from PyQt5.QtWidgets import QDialog, QDialogButtonBox

from forms.ui_transactiondescdialog import Ui_TransactionDescDialog


class TransactionDescDialog(QDialog, Ui_TransactionDescDialog):
    """The page to manage LN invoices"""

    def __init__(self, paymentDetails):
        super().__init__()
        self.setupUi(self)
        self.textEdit.setText("Currency: " + paymentDetails["currency"])
        self.textEdit.append("Created At: " + str(paymentDetails["created_at"]))
        self.textEdit.append("Expiry: " + str(paymentDetails["expiry"]))
        self.textEdit.append("Payee: " + paymentDetails["payee"])
        self.textEdit.append("Amount (mBTC): " + str(paymentDetails["msatoshi"]))
        self.textEdit.append("Description: " + paymentDetails["description"])
        self.textEdit.append(
            "min_final_cltv_expiry: " + str(paymentDetails["min_final_cltv_expiry"])
        )
        self.textEdit.append("Payment Secret: " + paymentDetails["payment_secret"])
        self.textEdit.append("Features: " + paymentDetails["features"])
        self.textEdit.append("Payment Hash: " + paymentDetails["payment_hash"])
        self.textEdit.append("Signature: " + paymentDetails["signature"])
        self.buttonBox.button(QDialogButtonBox.Close).clicked.connect(self.closeWindow)

    def closeWindow(self):
        self.close()
