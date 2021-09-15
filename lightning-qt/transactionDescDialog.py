from PyQt5.QtWidgets import QDialog, QDialogButtonBox

from forms.ui_transactiondescdialog import Ui_TransactionDescDialog


class TransactionDescDialog(QDialog, Ui_TransactionDescDialog):
    """The page to manage LN invoices"""

    def __init__(self, payment_details):
        super().__init__()
        self.setupUi(self)
        self.textEdit.setText("Currency: " + payment_details["currency"])
        self.textEdit.append("Created At: " + str(payment_details["created_at"]))
        self.textEdit.append("Expiry: " + str(payment_details["expiry"]))
        self.textEdit.append("Payee: " + payment_details["payee"])
        self.textEdit.append("Amount (mBTC): " + str(payment_details["msatoshi"]))
        self.textEdit.append("Description: " + payment_details["description"])
        self.textEdit.append(
            "min_final_cltv_expiry: " + str(payment_details["min_final_cltv_expiry"])
        )
        self.textEdit.append("Payment Secret: " + payment_details["payment_secret"])
        self.textEdit.append("Features: " + payment_details["features"])
        self.textEdit.append("Payment Hash: " + payment_details["payment_hash"])
        self.textEdit.append("Signature: " + payment_details["signature"])
        self.buttonBox.button(QDialogButtonBox.Close).clicked.connect(self.close_window)

    def close_window(self):
        self.close()
