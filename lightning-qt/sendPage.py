from PyQt5.QtWidgets import QWidget

from forms.ui_sendpage import Ui_SendPage


class SendPage(QWidget, Ui_SendPage):
    """The page to decode and/or pay bolt11 invoices"""

    def __init__(self, plugin):
        super().__init__()
        self.setupUi(self)
        self.plugin = plugin
        self.init_ui()

    def decode_invoice(self):
        """Decode the given bolt11 invoice"""
        invoice = self.plugin.rpc.decodepay(self.lineInvoice.text())
        # Condition to prevent for RPC errors
        if invoice:
            value = str(invoice["amount_msat"])
            if invoice["currency"] == "tb":
                value += " (testnet)"
            self.labelValue.setText(value)
            self.labelDescription.setText(invoice["description"])
            self.labelExpiry.setText(str(invoice["expiry"]))
            self.labelPublicKey.setText(invoice["payee"])

    def init_ui(self):
        """Initialize the UI by connecting actions"""
        self.buttonDecode.clicked.connect(self.decode_invoice)
        self.buttonPay.clicked.connect(self.pay_invoice)

    def pay_invoice(self):
        """Pay the given bolt11 invoice"""
        pay_return = self.plugin.rpc.pay(self.lineInvoice.text())
        # Condition to prevent for RPC errors
        if pay_return:
            if "payment_preimage" in pay_return:
                self.labelPaymentResult.setText(
                    "Succesfully paid invoice. Preimage: {}".format(
                        pay_return["payment_preimage"]
                    )
                )
            else:
                self.labelPaymentResult.setText(
                    "Could not pay invoice. Maybe you should open a channel with the payee"
                )
