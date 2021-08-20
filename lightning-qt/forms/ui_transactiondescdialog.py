# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'transactiondescdialog.ui'
#
# Created by: PyQt5 UI code generator 5.12.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_TransactionDescDialog(object):
    def setupUi(self, TransactionDescDialog):
        TransactionDescDialog.setObjectName("TransactionDescDialog")
        TransactionDescDialog.resize(560, 250)
        self.verticalLayout = QtWidgets.QVBoxLayout(TransactionDescDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.textEdit = QtWidgets.QTextEdit(TransactionDescDialog)
        self.textEdit.setObjectName("textEdit")
        self.verticalLayout.addWidget(self.textEdit)
        self.buttonBox = QtWidgets.QDialogButtonBox(TransactionDescDialog)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Close)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(TransactionDescDialog)
        QtCore.QMetaObject.connectSlotsByName(TransactionDescDialog)

    def retranslateUi(self, TransactionDescDialog):
        _translate = QtCore.QCoreApplication.translate
        TransactionDescDialog.setWindowTitle(_translate("TransactionDescDialog", "Transaction details"))


