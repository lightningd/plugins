from PyQt5.QtCore import Qt, QAbstractTableModel, QSortFilterProxyModel, QDateTime
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QMessageBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyledItemDelegate,
)
from PyQt5.QtGui import QIcon, QColor

from forms.ui_paymentsPage import Ui_PaymentsPage
from utils import timeout_bool
from transactionDescDialog import TransactionDescDialog

import datetime
import operator


class PaymentsPage(QWidget, Ui_PaymentsPage):
    """The page to display LN payments"""

    def __init__(self, plugin):
        super().__init__()
        self.payments_data = []
        self.setupUi(self)
        self.plugin = plugin
        self.payments_tableheaders = (
            "",
            "Date",
            "Type",
            "Label",
            "Payment Hash",
            "Amount (mBTC)",
            "",
        )
        self.payments_model = TableModel(self.payments_tableheaders)
        self.proxy_model = CustomSortingModel()
        self.proxy_model.setSourceModel(self.payments_model)
        self.populate_payments_data()
        self.payments_model.set_data(self.payments_data)
        self.paymentsTableView.setModel(self.proxy_model)
        self.paymentsTableView.sortByColumn(1, Qt.DescendingOrder)
        self.set_view()
        self.init_ui()

    def init_ui(self):
        """Initialize the UI by connecting actions"""
        self.paymentsTableView.doubleClicked.connect(self.show_details)

    def set_view(self):
        """Set the Table sizes"""
        self.paymentsTableView.setColumnWidth(0, 30)
        self.paymentsTableView.setColumnWidth(1, 140)
        self.paymentsTableView.setColumnWidth(2, 100)
        self.paymentsTableView.setColumnWidth(3, 500)
        self.paymentsTableView.setColumnWidth(4, 300)
        self.paymentsTableView.selectRow(0)
        self.paymentsTableView.setColumnHidden(6, True)
        self.paymentsTableView.setColumnHidden(4, True)

    def populate_payments(self):
        """Update payments list"""
        self.payments_model.layoutAboutToBeChanged.emit()
        self.populate_payments_data()
        self.payments_model.set_data(self.payments_data)
        self.payments_model.layoutChanged.emit()

    def populate_payments_data(self):
        """Update payments data"""
        self.payments_data = []
        """Update pays history list"""
        pays = self.plugin.rpc.listpays()
        # Condition to prevent RPC errors
        if pays:
            for pay in pays["pays"]:
                decoded_pay = self.plugin.rpc.decodepay(pay["bolt11"])
                if "label" in pay:
                    self.payments_data.append(
                        [
                            pay["status"],
                            datetime.datetime.fromtimestamp(decoded_pay["created_at"]),
                            "Pay",
                            pay["label"],
                            pay["payment_hash"],
                            decoded_pay["msatoshi"],
                            pay["bolt11"],
                        ]
                    )
                else:
                    self.payments_data.append(
                        [
                            pay["status"],
                            datetime.datetime.fromtimestamp(decoded_pay["created_at"]),
                            "Pay",
                            "-",
                            pay["payment_hash"],
                            decoded_pay["msatoshi"],
                            pay["bolt11"],
                        ]
                    )

        invoices = self.plugin.rpc.listinvoices()
        # Condition to prevent RPC errors
        if invoices:
            for invoice in invoices["invoices"]:
                decoded_pay = self.plugin.rpc.decodepay(invoice["bolt11"])
                if "label" in invoice:
                    self.payments_data.append(
                        [
                            invoice["status"],
                            datetime.datetime.fromtimestamp(decoded_pay["created_at"]),
                            "Invoice",
                            invoice["label"],
                            invoice["payment_hash"],
                            decoded_pay["msatoshi"],
                            invoice["bolt11"],
                        ]
                    )
                else:
                    self.payments_data.append(
                        [
                            invoice["status"],
                            datetime.datetime.fromtimestamp(decoded_pay["created_at"]),
                            "Invoice",
                            "-",
                            invoice["payment_hash"],
                            decoded_pay["msatoshi"],
                            invoice["bolt11"],
                        ]
                    )

    def show_details(self):
        index = self.paymentsTableView.currentIndex()
        value = index.sibling(index.row(), 6).data()
        decoded_pay = self.plugin.rpc.decodepay(value)

        dialog = TransactionDescDialog(decoded_pay)
        dialog.exec_()


class CustomSortingModel(QSortFilterProxyModel):
    def less_than(self, left, right):

        col = left.column()
        dataleft = left.data()
        dataright = right.data()

        if col == 1:
            dataleft = QDateTime.fromString(dataleft, "dd/MM/yyyy hh:mm")
            dataright = QDateTime.fromString(dataright, "dd/MM/yyyy hh:mm")

        return dataleft < dataright


class TableModel(QAbstractTableModel):
    def __init__(self, headerin):
        super(TableModel, self).__init__()
        self._arraydata = None
        self._headerdata = headerin

    def data(self, index, role):
        if role == Qt.DisplayRole and index.column() != 0:
            if index.column() == 3 and self._arraydata[index.row()][3] == "-":
                value = "(" + self._arraydata[index.row()][4] + ")"
            elif index.column() == 5 and self._arraydata[index.row()][2] == "Pay":
                value = self._arraydata[index.row()][5] * -1
            else:
                value = self._arraydata[index.row()][index.column()]
            if isinstance(value, datetime.datetime):
                return value.strftime("%d/%m/%Y" " %H:%M")
            return value
        if role == Qt.DecorationRole:
            if index.column() == 0:
                value = self._arraydata[index.row()][index.column()]
                if value == "complete" or value == "paid":
                    return QIcon(":/icons/success")
                elif value == "failed":
                    return QIcon(":/icons/failed")
                elif value == "expired":
                    return QIcon(":/icons/expired")
                elif value == "unpaid":
                    return QIcon(":/icons/pending")
            if index.column() == 3:
                value = self._arraydata[index.row()][index.column() - 1]
                if value == "Pay":
                    return QIcon(":/icons/send_black")
                elif value == "Invoice":
                    return QIcon(":/icons/receive_black")
        if role == Qt.BackgroundRole and index.row() % 2 == 1:
            return QColor(247, 247, 247)
        if role == Qt.ForegroundRole:
            value = self._arraydata[index.row()][0]
            if value == "expired" or value == "failed" or value == "unpaid":
                return QColor(140, 140, 140)
            if (
                index.column() == 5
                and self._arraydata[index.row()][index.column() - 3] == "Pay"
            ):
                return QColor(255, 0, 0)
            if (
                index.column() == 5
                and self._arraydata[index.row()][index.column() - 3] == "Invoice"
                and self._arraydata[index.row()][0] == "complete"
            ):
                return QColor(0, 255, 0)
        if role == Qt.TextAlignmentRole and index.column() == 5:
            return Qt.AlignRight | Qt.AlignVCenter
        if role == Qt.ToolTipRole:
            value = (
                self._arraydata[index.row()][0]
                + "\n "
                + self._arraydata[index.row()][1].strftime("%d/%m/%Y" " %H:%M")
                + "\n"
                + self._arraydata[index.row()][2]
                + "\n"
                + self._arraydata[index.row()][3]
                + "\n"
                + self._arraydata[index.row()][4]
                + "\n"
                + str(self._arraydata[index.row()][5])
            )
            return value

    def set_data(self, datain):
        self._arraydata = datain

    def row_count(self, index):
        # The length of the outer list.
        return len(self._arraydata)

    def column_count(self, index):
        return len(self._headerdata)

    def header_data(self, section, orientation, role):
        if role == Qt.TextAlignmentRole:
            if section == 5:
                return Qt.AlignRight | Qt.AlignVCenter
            else:
                return Qt.AlignLeft | Qt.AlignVCenter
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self._headerdata[section]
            elif orientation == Qt.Vertical:
                return self._headerdata[section]
        return None
