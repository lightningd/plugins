from PyQt5.QtWidgets import QWidget

from forms.ui_receivePage import Ui_ReceivePage


class ReceivePage(QWidget, Ui_ReceivePage):
    """The page to generate bolt11 invoices"""

    def __init__(self, plugin):
        super().__init__()
        self.setupUi(self)
        self.plugin = plugin
        self.init_ui()

    def clear_form(self):
        """Reset the form to the default values"""
        self.spinValue.setValue(1)
        self.lineLabel.setText("")
        self.lineDescription.setText("")
        self.spinExpiry.setValue(604800)  #  A week

    def generate_invoice(self):
        """Generate an invoice and display it"""
        amount_msat = self.spinValue.value()
        label = self.lineLabel.text()
        description = self.lineDescription.text()
        expiry = self.spinExpiry.value()
        invoice = self.plugin.rpc.invoice(amount_msat, label, description, expiry)
        # Condition to prevent RPC error
        if invoice:
            self.textResultInvoice.setText(invoice["bolt11"])

    def init_ui(self):
        """Initialize the UI by connecting actions"""
        self.buttonGenerate.clicked.connect(self.generate_invoice)
        self.buttonClear.clicked.connect(self.clear_form)
