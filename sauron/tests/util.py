import logging

from pyln.testing import utils


class LightningD(utils.LightningD):
    def __init__(self, lightning_dir, *args, **kwargs):
        super().__init__(lightning_dir, *args, **kwargs)

        opts_to_disable = [
            "bitcoin-datadir",
            "bitcoin-rpcpassword",
            "bitcoin-rpcuser",
            "dev-bitcoind-poll",
        ]
        for opt in opts_to_disable:
            self.opts.pop(opt)

    # Monkey patch
    def start(self, stdin=None, wait_for_initialized=True, stderr_redir=False):
        utils.TailableProc.start(
            self, stdin, stdout_redir=False, stderr_redir=stderr_redir
        )

        if wait_for_initialized:
            self.wait_for_log("Server started with public key")
        logging.info("LightningD started")
