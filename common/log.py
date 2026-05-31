import logging
import sys

logger = logging.getLogger('wechat-bot')
logger.setLevel(logging.DEBUG)
_handler = logging.StreamHandler(sys.stdout)
_handler.setLevel(logging.DEBUG)
_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(_handler)
