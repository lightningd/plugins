# Persistent Channels plugin

`lightningd` automatically tracks channels internally and will make
sure to reconnect to a peer if it has a channel open with it. However,
it only tracks the channel itself, it does not re-open a channel that
was closed.

The persistent channels plugin allows you to describe a number of
channels you'd like to have open at any time and the plugin will
attempt to maintain that state. The plugin keeps a list of desired
channels that should be opened and operational and will check every 30
seconds if it needs to open a new channel, or re-open a channel that
is currently being closed.
