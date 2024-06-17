from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
import json
import numpy as np
from numpy.typing import NDArray
import llguidance

from ._grammar import GrammarFunction, Terminal, Join
from .models._tokenizer import Tokenizer


class ParserException(Exception):
    def __init__(self, *args, **kwargs):
        self.current_byte = kwargs.pop("current_byte", None)
        self.allowed_bytes = kwargs.pop("allowed_bytes", None)
        self.consumed_bytes = kwargs.pop("consumed_bytes", None)
        super().__init__(*args, **kwargs)

@dataclass
class ParserState:
    tokens: List[int]
    ff_tokens: List[int]
    backtrack: int
    done: bool

@dataclass
class ParserResponse:
    new_bytes: bytes
    new_token_count: int
    new_bytes_prob: float
    is_generated: bool
    capture_groups: Dict[str, Union[bytes, List[bytes]]]
    capture_group_log_probs: Dict[str, Union[float, List[float]]]

@dataclass
class GenData:
    tokens: List[int]
    mask: NDArray[np.uint8]
    temperature: float

    def valid_next_tokens(self) -> List[int]:
        return np.where(self.mask)[0].tolist()

class Parser:
    """An abstract base class for guidance parsers."""
    pass

class LLParser(Parser):

    def __init__(
        self,
        grammar: GrammarFunction,
        tokenizer: Tokenizer,
        prompt: bytes = b"",
        ensure_bos_token: bool = True,
    ):
        # we can't have a terminal as the root
        if isinstance(grammar, Terminal):
            grammar = Join([grammar])

        self.grammar = grammar
        self.tokenizer = tokenizer

        self.ll_tokenizer = llguidance.LLTokenizer(
            llguidance.TokenizerWrapper(tokenizer)
        )
        self.ll_interpreter = llguidance.LLInterpreter(
            self.ll_tokenizer,
            json.dumps(grammar.ll_serialize()),
            log_level=2,
        )
        self._state = self._start(prompt=prompt, ensure_bos_token=ensure_bos_token)

    @property
    def done(self) -> bool:
        return self._state.done
    
    def advance(self) -> Tuple[Optional[GenData], ParserResponse]:
        gen_data, response, self._state = self._advance(self._state)
        return gen_data, response
    
    def consume_token(self, tok_id: int) -> None:
        self._state = self._consume_token(tok_id, self._state)

    def _start(self, prompt: bytes, ensure_bos_token: bool) -> ParserState:
        # add the beginning of sequence token if needed
        if (
            ensure_bos_token
            and self.tokenizer.bos_token is not None
            and not prompt.startswith(self.tokenizer.bos_token)
        ):
            prompt = self.tokenizer.bos_token + prompt
        prompt_tokens = self.tokenizer.encode(prompt)

        return ParserState(
            tokens=self.ll_interpreter.process_prompt(prompt_tokens),
            ff_tokens=[],
            backtrack=0,
            done=False,
        )

    def _advance(self, state: ParserState) -> Tuple[Optional[GenData], ParserResponse, ParserState]:
        mask, resp = self.ll_interpreter.mid_process(state.backtrack, state.ff_tokens)
        r = json.loads(resp)

        backtrack = r["backtrack"]
        ff_tokens = r["ff_tokens"]
        done = r["stop"]

        tokens = state.tokens
        if mask is not None:
            assert not done
            assert backtrack == 0
            assert len(ff_tokens) == 0
            gen_data = GenData(
                tokens=tokens,
                mask=np.frombuffer(mask, dtype=np.uint8),
                temperature=r["temperature"],
            )
        else:
            if backtrack:
                tokens = tokens[:-backtrack]
            tokens = tokens + ff_tokens
            gen_data = None

        response = self._handle_progress(r["progress"])
        state = ParserState(
            tokens=tokens,
            ff_tokens=ff_tokens,
            backtrack=backtrack,
            done=done,
        )
        return gen_data, response, state

    def _consume_token(self, tok_id: int, state: ParserState) -> ParserState:
        assert not state.done
        assert state.backtrack == 0
        assert len(state.ff_tokens) == 0
        return ParserState(
            tokens=state.tokens + [tok_id],
            ff_tokens=[tok_id],
            backtrack=0,
            done=False,
        )

    @staticmethod
    def _handle_progress(progress: List[dict]) -> ParserResponse:
        new_bytes = b""
        new_token_count = 0
        new_bytes_prob = 0.0
        is_generated = False
        capture_groups: Dict[str, Any] = {}
        capture_group_log_probs: Dict[str, Any] = {}
        num_text_entries = 0

        for j in progress:
            tag = j.get("object", "")
            if tag == "capture":
                is_generated = True
                cname: str = j["name"]
                data = bytes.fromhex(j["hex"])
                if cname.startswith("__LIST_APPEND:"):
                    cname = cname[14:]
                    if cname not in capture_groups or \
                        not isinstance(capture_groups[cname], list):
                        capture_groups[cname] = []
                        capture_group_log_probs[cname] = []
                    capture_groups[cname].append(data)
                    capture_group_log_probs[cname].append(j["log_prob"])
                else:
                    capture_groups[cname] = data
                    capture_group_log_probs[cname] = j["log_prob"]
            elif tag == "text":
                # it actually should only happen once per round...
                new_bytes += bytes.fromhex(j["hex"])
                new_token_count += j["num_tokens"]
                new_bytes_prob += j["log_prob"]
                is_generated |= j["is_generated"]
                num_text_entries += 1
        if num_text_entries > 0:
            new_bytes_prob /= num_text_entries

        return ParserResponse(
            new_bytes=new_bytes,
            new_token_count=new_token_count,
            new_bytes_prob=new_bytes_prob,
            is_generated=is_generated,
            capture_groups=capture_groups,
            capture_group_log_probs=capture_group_log_probs,
        )
    
from .models._byte_tokenizer import ByteTokenizer    
class ByteParser(Parser):
    def __init__(
        self,
        grammar: GrammarFunction,
        prompt: bytes = b"",
        ensure_bos_token: bool = True,
    ):
        self.tokenizer = ByteTokenizer()
        self.ll_parser = LLParser(grammar, self.tokenizer, prompt, ensure_bos_token)
        self.bytes = b""
        self.gen_data: Optional[GenData] = None
        self.pos = 0
        self._variables = {}
        self._variables_log_probs = {}

    def matched(self) -> bool:
        if self.pos < len(self.bytes):
            return False
        if not self.ll_parser.done:
            # May need to do a final advance
            self.consume_bytes(b"")
        return self.ll_parser.done

    def consume_bytes(self, bts: bytes) -> None:
        while self.gen_data is None and not self.ll_parser.done:
            self.gen_data, response = self.ll_parser.advance()
            self._update_capture(response)
            self.bytes += response.new_bytes
        
        if not bts:
            return
        
        b = bts[0]
        if self.pos < len(self.bytes):
            if b != self.bytes[self.pos]:
                raise ParserException(
                    f"Expected byte {bytes([self.bytes[self.pos]])!r} (fast_forward), got {bytes([b])!r}",
                    current_byte=b,
                    allowed_bytes=[self.bytes[self.pos]],
                    consumed_bytes=self.bytes,
                )
            self.pos += 1
            self.consume_bytes(bts[1:])
        else:
            assert self.gen_data is not None
            valid_next_tokens = self.gen_data.valid_next_tokens()
            if b not in valid_next_tokens:
                valid_next_bytes = [bytes([t]) for t in valid_next_tokens]
                raise ParserException(
                    f"Expected one of the following bytes: {valid_next_bytes!r}, got {bytes([b])!r}",
                    current_byte=b,
                    allowed_bytes=valid_next_bytes,
                    consumed_bytes=self.bytes,
                )
            self.ll_parser.consume_token(b)
            # Reset gen_data as we are done with it
            self.gen_data = None
            # Reconsume byte again
            self.consume_bytes(bts)

    def get_captures(self):
        return self._variables, self._variables_log_probs
    
    def _update_capture(self, response):
        # Stolen from model. TODO: refactor
        for k in response.capture_groups:
            v = response.capture_groups[k]

            # see if we are in a list_append mode
            if isinstance(v, list):
                for i, inner_v in enumerate(v):
                    # convert to a string if possible
                    # TODO: will need to not just always do this once we support images etc.
                    try:
                        inner_v = (
                            inner_v.decode("utf8")
                            if isinstance(inner_v, bytes)
                            else inner_v
                        )
                    except UnicodeDecodeError:
                        pass

                    if k not in self._variables or not isinstance(self._variables[k], list):
                        self._variables[k] = []
                        self._variables_log_probs[k] = []
                    self._variables[k].append(inner_v)
                    self._variables_log_probs[k].append(
                        response.capture_group_log_probs[k][i]
                    )

            # ...or standard assignment mode
            else:
                # convert to a string if possible
                # TODO: will need to not just always do this once we support images etc.
                try:
                    v = v.decode("utf8") if isinstance(v, bytes) else v
                except UnicodeDecodeError:
                    pass
                self._variables[k] = v
                self._variables_log_probs[k] = response.capture_group_log_probs[k]