# Commando plugin

This plugin allows other nodes to send your node commands, and allows you
to send them to other nodes.  The nodes must be authorized, and must be
directly connected.

Motto: Reckless?  Try going commando!

## Installation

For general plugin installation instructions see the repos main
[README.md](https://github.com/lightningd/plugins/blob/master/README.md#Installation)

## Options:

Each of these can be specified more than once:

* --commando-reader: a node id which can execute `list` and `get` commands
* --commando-writer: a node id which can execute any commands.

## Example Usage

$ l1-cli plugin start commando.py commando_reader=0266e4598d1d3c415f572a8488830b60f7e744ed9235eb0b1ba93283b315c03518
$ l2-cli plugin start commando.py
$ l2-cli commando 022d223620a359a47ff7f7ac447c85c46c923da53389221a0054c11c1e3ca31d59 stop


