import logging
import io
import json
import re
import os
from typing import Any, Dict, Iterator, List, Optional, Tuple

import numpy as np
import torch
import llguidance
from transformers import AutoModelForCausalLM, AutoProcessor

from guidance._parser import TokenParser, process_grammar, process_prompt
from guidance._schema import EngineCallResponse, GuidanceEngineMetrics
from guidance.models._model import (
    Engine,
    Model,
    modality_pattern,
    Modality
)
# from guidance.models.transformers._transformers import TransformersTokenizer
from guidance.chat import ChatMLTemplate
from guidance.models.transformers._transformers import TransformersTokenizer

try:
    from PIL import Image
    has_pillow = True
except ModuleNotFoundError:
    has_pillow = False

logger = logging.getLogger(__name__)


class TransformersPhi3VisionEngine(Engine):
    def __init__(
        self,
        model="microsoft/Phi-3-vision-128k-instruct",
        compute_log_probs=False,
        **kwargs,
    ):
        if not has_pillow:
            raise Exception("Please install pillow with `pip install pillow` to use Phi 3 Vision")
        self.model_name = model
        # Initialize the underlying Phi 3 Vision model
        self.model_obj = AutoModelForCausalLM.from_pretrained(model, **kwargs)
        self.device = self.model_obj.device

        # Processor handles tokenization and image processing
        self.processor = AutoProcessor.from_pretrained(self.model_name, trust_remote_code=True)
        super().__init__(self.processor.tokenizer, compute_log_probs)
        self.tokenizer = TransformersTokenizer(model, self.processor.tokenizer, sp_whitespace=True)

        # Cache for past key values
        self._past_key_values = None
        self._cached_token_ids: list[int] = []

        # Track last image token position for cache invalidation
        # self._last_image_token_position = -1


    def start(self, prompt, grammar, media: dict, ensure_bos_token=True) -> TokenParser:
        if isinstance(prompt, bytes):
            prompt = prompt.decode("utf-8")
        elif isinstance(prompt, str):
            prompt = prompt
        elif isinstance(prompt, TokenParser):
            raise NotImplementedError(
                "Still need to implement support for extending a full Parser state."
            )
        else:
            raise Exception("The passed prompt is of an unknown type!")

        # Map Guidance placeholders to Phi 3 Vision format
        # and make list of images for processing
        images = []
        processed_prompt = prompt
        matches = {}
        for match in modality_pattern.finditer(prompt):
            match_str = match.group(0)
            modality_type = match.group(1)
            if modality_type != Modality.IMAGE.name:
                logger.debug("Skipping non-image modality: %s", match_str)
                continue
            media_id = match.group(2)
            if match_str not in matches:
                matches[match_str] = media_id 

        image_counter = 1
        for match in matches.keys():
            processed_prompt = processed_prompt.replace(
                match, f"<|image_{image_counter}|>"
            )
            media_key = matches[match]
            images.append(Image.open(io.BytesIO(media[media_key])))
            image_counter += 1
        logger.debug("Transformed prompt: %s -> ", prompt, processed_prompt)

        # TODO - save these for inputs for later?
        model_inputs = self.processor(
            text=processed_prompt,
            images=images if len(images) > 0 else None,
            return_tensors="pt",
        ).to(self.device)

        # We will reuse everything except input_ids (attention_mask, pixel_values, image_sizes)
        self.model_inputs = model_inputs

        tokens = model_inputs["input_ids"][0].tolist()

        serialized_grammar = process_grammar(grammar)
        ll_tokenizer = llguidance.LLTokenizer(
            llguidance.TokenizerWrapper(self.tokenizer)
        )
        ll_interpreter = llguidance.LLInterpreter(
            ll_tokenizer,
            serialized_grammar,
            log_level=int(os.environ.get("LLGUIDANCE_LOG_LEVEL", "1")),
        )
        if ensure_bos_token and self.tokenizer.bos_token_id is not None:
            bos_token_id = self.tokenizer.bos_token_id
        else:
            bos_token_id = None

        # Find the last multimodal (negative) token in the sequence, if any
        last_multimodal_index = -1
        for i, token in enumerate(reversed(tokens)):
            if token < 0:
                last_multimodal_index = len(tokens) - i - 1
                break

        # We'll process tokens starting from the last multimodal token
        if last_multimodal_index != -1:
            processed_tokens = process_prompt(tokens[last_multimodal_index+1:], ll_interpreter, bos_token_id)
            prompt_tokens = tokens[:last_multimodal_index+1] + processed_tokens
        else:
            prompt_tokens = process_prompt(tokens, ll_interpreter, bos_token_id)

        return TokenParser(ll_interpreter, prompt_tokens)


    def get_logits(self, prompt: bytes, token_ids: list[int], media: Optional[dict]=None):
        """Computes the logits for the given token state.

        This overrides a method from the LocalEngine class that is used to get
        inference results from the model.
        """

        # make sure we don't run off the end of the model
        if len(token_ids) >= getattr(self.model_obj.config, "max_position_embeddings", 1e10):
            raise Exception(
                f"Attempted to run a transformers model past its maximum context window size of {self.model_obj.config.max_position_embeddings}!"
            )

        # get the number of cache positions we are using
        # cache_token_ids = self._cached_token_ids
        # num_cached = 0
        # for id in cache_token_ids:
        #     if (
        #         num_cached >= len(cache_token_ids)
        #         or num_cached >= len(token_ids)
        #         or token_ids[num_cached] != id
        #     ):
        #         break
        #     num_cached += 1

        # reset the cache length according to that number of positions
        # past_key_values = self._past_key_values
        # past_length = past_key_values[0][0].size(-2) if past_key_values is not None else 0
        # if past_length > num_cached:
        #     # note we recompute the last token because we don't bother to handle the special case of just computing logits
        #     past_length = max(0, num_cached - 1)
        #     self._past_key_values = tuple(
        #         tuple(p[..., :past_length, :] for p in v) for v in past_key_values
        #     )
        # cache_token_ids[past_length:] = []

        # call the model
        # new_token_ids = token_ids[past_length:]
        def prep_input(input_tensor):
            return torch.tensor(input_tensor).unsqueeze(0).to(self.device)

        if len(token_ids) > 0:
            input_ids = prep_input(token_ids)
            self.model_inputs["input_ids"] = input_ids
            self.model_inputs["attention_mask"]=torch.ones(1, len(token_ids)).to(self.device)
            # pixel_values = prep_input(self.model_inputs["pixel_values"]) if "pixel_values" in self.model_inputs else None
            # image_sizes = prep_input(self.model_inputs["image_sizes"]) if "image_sizes" in self.model_inputs else None
            with torch.no_grad():
                model_out = self.model_obj(
                    **self.model_inputs,
                    # input_ids=input_ids,
                    # pixel_values=pixel_values,
                    # image_sizes=image_sizes,
                    # past_key_values=self._past_key_values,
                    # use_cache=True,
                    return_dict=True,
                    output_attentions=False,
                    output_hidden_states=False,
                )

            # save the results
            # self._past_key_values = model_out.past_key_values
            # cache_token_ids.extend(new_token_ids)
            # # Need to add special truncating logic here for weird models that have a different output size than tokenizer vocab
            self._cached_logits = (
                model_out.logits[0, -1, : len(self.tokenizer.tokens)].cpu().numpy()
            )
            self.metrics.engine_input_tokens += len(token_ids)
            self.metrics.engine_output_tokens += 1

        return self._cached_logits

    # def _find_last_image_token_position(self, tokens: list[int]) -> int:
    #     """Find the position of the last negative token (image placeholder)."""
    #     for i, token in enumerate(reversed(tokens)):
    #         if token < 0:
    #             return len(tokens) - i - 1
    #     return -1


class TransformersPhi3Vision(Model):
    def __init__(
        self,
        model=None,
        echo=True,
        compute_log_probs=False,
        **kwargs,
    ):
        """Build a new TransformersPhi3Model object."""
        if model is None or len(model) == 0:
            model = "microsoft/Phi-3-vision-128k-instruct"
        super().__init__(
            TransformersPhi3VisionEngine(
                model,
                compute_log_probs,
                **kwargs,
            ),
            echo=echo,
        )