from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QLabel

from forms.ui_channelsPage import Ui_ChannelsPage
from utils import timeout_bool


class ChannelsPage(QWidget, Ui_ChannelsPage):
    """The page to manage LN channels"""

    def __init__(self, plugin):
        super().__init__()
        self.setupUi(self)
        self.plugin = plugin
        self.init_ui()
        self.populate_channels()

    def clear(self):
        """Reset all the child widget to their default value"""
        self.lineNewChannelId.setText("")
        self.labelNewChannelResult.setText("")
        self.lineCloseId.setText("")
        self.labelCloseResult.setText("")
        self.lineSetFeesId.setText("")
        self.labelSetFeesResult.setText("")
        self.checkCloseForce.setChecked(False)
        while self.layoutChannelId.count() > 2:
            self.layoutChannelId.takeAt(2).widget().deleteLater()
        while self.layoutNodeId.count() > 2:
            self.layoutNodeId.takeAt(2).widget().deleteLater()
        while self.layoutAmount.count() > 2:
            self.layoutAmount.takeAt(2).widget().deleteLater()
        while self.layoutIncoming.count() > 2:
            self.layoutIncoming.takeAt(2).widget().deleteLater()

    def close_channel(self):
        """Close the channel specified by the user"""
        self.labelCloseResult.setText("Sending closing request..")
        self.labelCloseResult.repaint()
        closing_result = self.plugin.rpc.close(
            self.lineCloseId.text(),
            self.checkCloseForce.isChecked(),
            self.spinCloseTimeout.value(),
        )
        if closing_result:
            if "txid" in closing_result:
                self.labelCloseResult.setText(
                    "{} closed channel at {}".format(
                        closing_result["type"], closing_result["txid"]
                    )
                )
            else:
                self.labelCloseResult.setText(
                    "Could not close the channel before\
                        timeout. Channel might still be closed in the future."
                )
        else:
            self.labelCloseResult.setText("")

    def create_channel(self):
        """Connect to a peer and fund a channel with it"""
        peer = self.lineNewChannelId.text()
        self.labelNewChannelResult.setText("Connecting to peer..")
        self.labelNewChannelResult.repaint()
        # Condtion for RPC error in slots
        if timeout_bool(2, self.plugin.rpc.connect, peer):
            peer_id = peer.split("@")[0]
            self.labelNewChannelResult.setText("Funding the channel..")
            self.labelNewChannelResult.repaint()
            fund_result = self.plugin.rpc.fundchannel(
                peer_id,
                self.spinNewChannelAmount.value(),
                announce=not self.checkPrivateChannel.isChecked(),
            )
            # Condtion for RPC error in slots
            if fund_result:
                self.labelNewChannelResult.setText(
                    "Succesfully created the channel.\nFunding tx : {}".format(
                        str(fund_result["txid"])
                    )
                )
        else:
            self.labelNewChannelResult.setText(
                "Could not connect to peer, connection timed out."
            )

    def init_ui(self):
        """Initialize the UI by connecting actions"""
        self.buttonNewChannel.clicked.connect(self.create_channel)
        self.buttonCloseChannel.clicked.connect(self.close_channel)
        self.buttonSetFees.clicked.connect(self.set_routing_fees)

    def populate_channels(self):
        """Update channels list"""
        funds = self.plugin.rpc.listfunds()
        # Condition to prevent RPC errors
        if funds:
            for channel in funds["channels"]:
                if "short_channel_id" in channel:
                    # Only populate with settled channels
                    channel_id = QLabel(channel["short_channel_id"])
                    channel_id.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    self.layoutChannelId.addWidget(channel_id)
                    peer_id = QLabel(channel["peer_id"])
                    peer_id.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    peer_id.setWordWrap(True)
                    peer_id.setFixedWidth(200)  # TODO: Handle this
                    self.layoutNodeId.addWidget(peer_id)
                    our_amount = QLabel(str(channel["our_amount_msat"])[:-4])
                    our_amount.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    our_amount.setAlignment(Qt.AlignRight)
                    self.layoutAmount.addWidget(our_amount)
                    their_amount = QLabel(
                        str(
                            (channel["channel_total_sat"] - channel["channel_sat"])
                            * 1000
                        )
                    )
                    their_amount.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    their_amount.setAlignment(Qt.AlignRight)
                    self.layoutIncoming.addWidget(their_amount)

    def set_routing_fees(self):
        """Set a channel (or global) routing fees"""
        id_ = self.lineSetFeesId.text() or "all"
        set_result = self.plugin.rpc.setchannelfee(
            id_, base=self.spinSetFeesBase.value(), ppm=self.spinSetFeesPpm.value()
        )
        if set_result:
            self.labelSetFeesResult.setText(
                "Succesfully set fees. Base : {}, ppm : {}".format(
                    set_result["base"], set_result["ppm"]
                )
            )
