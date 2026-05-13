import logging

from pyln.testing import utils


class LightningD(utils.LightningD):
    # Monkey patch
    def start(self, stdin=None, wait_for_initialized=True, stderr_redir=False):
        utils.TailableProc.start(
            self, stdin, stdout_redir=False, stderr_redir=stderr_redir
        )

        if wait_for_initialized:
            self.wait_for_log("Server started with public key")
        logging.info("LightningD started")
