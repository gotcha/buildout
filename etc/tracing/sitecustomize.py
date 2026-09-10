# Auto-start MonkeyType tracing in every Python process that has this
# directory on PYTHONPATH. Used by the experimental "traced" test suite.
# Never break the host process: any failure disables tracing silently.
try:
    import atexit
    import sys

    from monkeytype.config import DefaultConfig
    from monkeytype.tracing import CallTracer

    _config = DefaultConfig()
    _logger = _config.trace_logger()
    _tracer = CallTracer(
        logger=_logger,
        max_typed_dict_size=_config.max_typed_dict_size(),
        code_filter=_config.code_filter(),
    )
    sys.setprofile(_tracer)
    atexit.register(_logger.flush)
except Exception:
    import os
    if os.environ.get('MT_TRACING_DEBUG'):
        import traceback
        traceback.print_exc()
