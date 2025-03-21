""" Metrics that arise from both language models and its execution environment."""

import time
from asyncio import CancelledError
from enum import Enum
from multiprocessing import Manager, Process
from typing import Union, Any
import logging

import numpy as np
import psutil

from .._schema import GuidanceEngineMetrics
from ..models import Model
from ..registry import get_renderer, get_bg_async

from ..visual import MetricMessage

logger = logging.getLogger(__name__)


class PeriodicMetricsGenerator:
    def __init__(self, monitor: "Monitor", sleep_sec=0.5):
        self._monitor = monitor
        self._sleep_sec = sleep_sec
        self._task = None
        self._task_cancelled = False
        self._is_paused = False
        get_bg_async().run_async_coroutine(self._emit())

    def start(self):
        self._task = get_bg_async().run_async_coroutine(get_bg_async().async_task(self._emit())).result()

    def stop(self):
        if self._task is not None:
            self._task.cancel()
            # TODO: it seems _task.cancel() is not working, use a flag to stop the task
            self._task_cancelled = True

    def pause(self):
        """
        Pauses the model by setting the internal _is_paused flag to True.

        This method can be used to temporarily halt the model's operations.
        """
        self._is_paused = True

    def resume(self):
        """
        Resume the model's operation by setting the paused state to False.

        This method changes the internal state of the model to indicate that it is no longer paused.
        """
        self._is_paused = False

    async def _emit(self):
        import asyncio
        import time

        time_start = time.time()
        while not self._task_cancelled:
            try:
                await asyncio.sleep(self._sleep_sec)

                cpu_percent = self._monitor.get_metric(MonitoringMetric.CPU_USAGE)
                used_ram = self._monitor.get_metric(MonitoringMetric.MEM_USAGE)
                gpu_percent = self._monitor.get_metric(MonitoringMetric.GPU_USAGE)
                gpu_used_vram = self._monitor.get_metric(MonitoringMetric.GPU_USED_MEM)

                if gpu_percent:
                    gpu_percent = max(gpu_percent)
                else:
                    gpu_percent = 0

                if gpu_used_vram:
                    gpu_used_vram = max(gpu_used_vram)
                else:
                    gpu_used_vram = 0

                if not cpu_percent:
                    cpu_percent = 0

                if not used_ram:
                    used_ram = 0

                time_end = time.time()
                time_elapsed = time_end - time_start

                if not self._is_paused:
                    renderer = get_renderer()
                    renderer.update(MetricMessage(name="wall time", value=time_elapsed))
                    renderer.update(MetricMessage(name="cpu", value=cpu_percent))
                    renderer.update(MetricMessage(name="ram", value=used_ram))
                    renderer.update(MetricMessage(name="gpu", value=gpu_percent))
                    renderer.update(MetricMessage(name="vram", value=gpu_used_vram))
            except CancelledError:
                logger.debug("METRICGEN:canceling")
                break
            except Exception as e:
                logger.debug(f"METRICGEN: {repr(e)}")
                break

        logger.debug("METRICGEN:exiting")


class PostExecMetrics:
    def __init__(self, monitor: "Monitor"):
        self._monitor = monitor

    def emit_messages(self, lm: "Model"):
        token_reduction = self._monitor.get_metric(MonitoringMetric.TOKEN_REDUCTION, lm)
        renderer = get_renderer()
        if token_reduction is not None:
            renderer.update(
                MetricMessage(
                    name="token reduction",
                    value=token_reduction * 100,
                )
            )

        output_tokens = self._monitor.get_metric(MonitoringMetric.OUTPUT_TOKENS, lm)
        if output_tokens is not None:
            renderer.update(MetricMessage(name="consumed", value=output_tokens))

        avg_latency = self._monitor.get_metric(MonitoringMetric.AVG_LATENCY, lm)
        if avg_latency is not None:
            renderer.update(MetricMessage(name="avg latency", value=avg_latency))


class MonitoringMetric(str, Enum):
    CPU_USAGE = "cpu_usage"
    MEM_USAGE = "mem_usage"
    GPU_USAGE = "gpu_usage"
    GPU_USED_MEM = "gpu_used_mem"
    GPU_TOTAL_MEM = "gpu_total_mem"
    INPUT_TOKENS = "input_tokens"
    OUTPUT_TOKENS = "output_tokens"
    BACKTRACK_TOKENS = "backtrack_tokens"
    TOKEN_COUNT = "token_count"
    TOKEN_REDUCTION = "token_reduction"
    AVG_LATENCY = "avg_latency"


ALL_METRICS = [
    MonitoringMetric.CPU_USAGE,
    MonitoringMetric.MEM_USAGE,
    MonitoringMetric.GPU_USAGE,
    MonitoringMetric.GPU_USED_MEM,
    MonitoringMetric.GPU_TOTAL_MEM,
    MonitoringMetric.INPUT_TOKENS,
    MonitoringMetric.OUTPUT_TOKENS,
    MonitoringMetric.BACKTRACK_TOKENS,
    MonitoringMetric.TOKEN_COUNT,
    MonitoringMetric.TOKEN_REDUCTION,
    MonitoringMetric.AVG_LATENCY,
]


def _monitor_fn(
    stop_flag,
    metrics_dict: dict[MonitoringMetric, list],
    max_size: int = 100,
    interval_ms: float = 1000,
):
    # print("Monitoring started")

    to_collect_gpu_stats = False
    has_gpustat = False
    try:
        import gpustat

        has_gpustat = True
    except:
        logger.warning("gpustat is not installed, run `pip install gpustat` to collect GPU stats.")

    if has_gpustat:
        try:
            gpu_stats = gpustat.GPUStatCollection.new_query()
            if len(gpu_stats) > 0:
                # only collect GPU stats if there is at least one GPU
                to_collect_gpu_stats = True
        except:
            logger.warning("Non-Nvidia GPU monitoring is not supported in this version.")

    try:
        while not stop_flag.value:
            t0 = time.time()

            # cpu_percent = psutil.cpu_percent(interval=1)
            cpu_percent = psutil.cpu_percent() / 100.0
            memory_usage = psutil.virtual_memory()

            metrics_dict[MonitoringMetric.CPU_USAGE].append(cpu_percent)
            metrics_dict[MonitoringMetric.MEM_USAGE].append(memory_usage.used / (1024**3))

            if to_collect_gpu_stats:
                gpu_stats = gpustat.GPUStatCollection.new_query()

                usage = [gpu.utilization / 100.0 for gpu in gpu_stats.gpus]
                mem_usage = [gpu.memory_used for gpu in gpu_stats.gpus]
                mem_total = [gpu.memory_total for gpu in gpu_stats.gpus]

                metrics_dict[MonitoringMetric.GPU_USAGE].append(usage)
                metrics_dict[MonitoringMetric.GPU_USED_MEM].append(mem_usage)
                metrics_dict[MonitoringMetric.GPU_TOTAL_MEM].append(mem_total)

            for metrics in metrics_dict.values():
                if len(metrics) > max_size:
                    metrics.pop(0)

            lat = time.time() - t0

            # sleep for the remaining time of the interval
            sleep_time = interval_ms / 1000.0 - lat
            if sleep_time < 0:
                time.sleep(sleep_time)
    except Exception as e:
        # print(f"Error in monitoring: {e}")
        pass

    # print("Monitoring stopped")


class Monitor:
    """Monitoring service to collect necessary metrics for visualization"""

    def __init__(self, engine_metrics: GuidanceEngineMetrics, **kwargs):
        self.engine_metrics = engine_metrics
        self.mp_manager = Manager()

        # use list instead of queue for easily accessing each item, e.g., last item
        self.max_size = kwargs.get("max_size", 100)

        self.metrics_dict = {
            MonitoringMetric.CPU_USAGE: self.mp_manager.list(),
            MonitoringMetric.MEM_USAGE: self.mp_manager.list(),
            MonitoringMetric.GPU_USAGE: self.mp_manager.list(),
            MonitoringMetric.GPU_USED_MEM: self.mp_manager.list(),
            MonitoringMetric.GPU_TOTAL_MEM: self.mp_manager.list(),
        }

        self.stop_flag = self.mp_manager.Value("b", False)
        self.process = None

        self.per_token_metrics = []  # store metrics per token in token list

    def start(self):
        self.process = Process(
            target=_monitor_fn, args=(self.stop_flag, self.metrics_dict, self.max_size)
        )
        self.process.start()
        logger.debug("MONITOR:start")

    def stop(self):
        if self.process:
            self.stop_flag.value = True
            self.process.terminate()

            for metrics in self.metrics_dict.values():
                metrics[:] = []  # NOTE(nopdive): ListProxy does not have .clear method.
        logger.debug("MONITOR:stop")

    def reset(self):
        self.stop()

        for metrics in self.metrics_dict.values():
            metrics.clear()

        self.start()
        logger.debug("MONITOR:reset")

    def get_metrics(
        self, metrics=None, lm: Union["Model", None] = None
    ) -> dict[MonitoringMetric, Any]:
        if metrics is None:
            metrics = ALL_METRICS
        result = {}

        for metric in metrics:
            if metric in [
                MonitoringMetric.CPU_USAGE,
                MonitoringMetric.MEM_USAGE,
                MonitoringMetric.GPU_USAGE,
                MonitoringMetric.GPU_USED_MEM,
                MonitoringMetric.GPU_TOTAL_MEM,
            ]:
                result[metric] = (
                    self.metrics_dict[metric][-1] if len(self.metrics_dict[metric]) > 0 else None
                )
            elif metric == MonitoringMetric.INPUT_TOKENS:
                result[metric] = self.engine_metrics.engine_input_tokens
            elif metric == MonitoringMetric.OUTPUT_TOKENS:
                result[metric] = self.engine_metrics.engine_output_tokens
            elif metric == MonitoringMetric.BACKTRACK_TOKENS:
                result[metric] = self.engine_metrics.engine_backtrack_tokens
            elif metric == MonitoringMetric.TOKEN_COUNT:
                result[metric] = lm.token_count if lm is not None else None
            elif metric == MonitoringMetric.TOKEN_REDUCTION:
                if lm is not None and lm.token_count > 0:
                    result[metric] = 1 - min(1, (lm.metrics.engine_output_tokens / lm.token_count))
                else:
                    result[metric] = None
            elif metric == MonitoringMetric.AVG_LATENCY:
                if lm is None:
                    result[metric] = None
                else:
                    lats = []
                    model = lm
                    while model._parent is not None:
                        if model.vis_chunk:
                            for token in model.vis_chunk.generated_tokens:
                                lats.append(token.latency_ms)
                            for token in model.vis_chunk.force_forwarded_tokens:
                                lats.append(token.latency_ms)
                        model = model._parent

                    if len(lats) == 0:
                        result[metric] = None
                    else:
                        result[metric] = np.mean(lats)

        return result

    def get_metric(self, metric: MonitoringMetric, lm: Union["Model", None] = None) -> Any:
        return self.get_metrics([metric], lm)[metric]
