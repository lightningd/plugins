# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'forms/paymentspage.ui'
#
# Created by: PyQt5 UI code generator 5.12.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_PaymentsPage(object):
    def setupUi(self, PaymentsPage):
        PaymentsPage.setObjectName("PaymentsPage")
        PaymentsPage.resize(858, 350)
        self.verticalLayout = QtWidgets.QVBoxLayout(PaymentsPage)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.verticalFrame = QtWidgets.QFrame(PaymentsPage)
        self.verticalFrame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.verticalFrame.setObjectName("verticalFrame")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.verticalFrame)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.paymentsTableView = QtWidgets.QTableView(self.verticalFrame)
        self.paymentsTableView.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.paymentsTableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.paymentsTableView.setSortingEnabled(True)
        self.paymentsTableView.setObjectName("paymentsTableView")
        self.paymentsTableView.horizontalHeader().setCascadingSectionResizes(False)
        self.paymentsTableView.horizontalHeader().setMinimumSectionSize(0)
        self.paymentsTableView.horizontalHeader().setStretchLastSection(True)
        self.paymentsTableView.verticalHeader().setVisible(False)
        self.paymentsTableView.verticalHeader().setHighlightSections(True)
        self.verticalLayout_2.addWidget(self.paymentsTableView)
        self.horizontalLayout.addWidget(self.verticalFrame)
        self.verticalLayout.addLayout(self.horizontalLayout)

        self.retranslateUi(PaymentsPage)
        QtCore.QMetaObject.connectSlotsByName(PaymentsPage)

    def retranslateUi(self, PaymentsPage):
        _translate = QtCore.QCoreApplication.translate
        PaymentsPage.setWindowTitle(_translate("PaymentsPage", "Form"))


