# ZeroMQ Publisher Plugin

This module forwards [notifications](https://github.com/ElementsProject/lightning/blob/master/doc/PLUGINS.md#notification-types) to ZeroMQ endpoints depending on configuration.

The usage and setup mimics [similar functionality in `bitcoind`](https://github.com/bitcoin/bitcoin/blob/master/doc/zmq.md) for opting-in to notifications and selecting [high water mark (ZMQ\_HWM)](http://api.zeromq.org/2-1:zmq-setsockopt) preferences.


## Dependencies

[Twisted](https://twistedmatrix.com) and [txZMQ](https://pypi.org/project/txZMQ/) are used by this plugin.

```
$ sudo pip3 install -r requirements
```

## Installation

For general plugin installation instructions see the repos main
[README.md](https://github.com/lightningd/plugins/blob/master/README.md#Installation)

## Usage

The plugin registeres CLI options for opting in to notifications at given endpoints.
Eg running with:
```
 $ lightningd --zmq-pub-connect=ipc:///tmp/cl-zmq  \
              --zmq-pub-disconnect=tcp://127.0.0.1:5555
```
will publish `connect` and `disconnect` notifications to the specified endpoints. The default high water mark is 1000, which is the same as `bitcoind`'s default.

This plugin does not interpret the content of the data, merely passes it on.

The ZMQ `tag` used for subscribing is the UTF-8 encoded string of the notification type name string.
Eg. for the `invoice_payment` notification, the tag for subscribers will be `b'invoice_payment'`. The data published will be UTF-8 encoded JSON which comes from `lightningd`.

## Example

[example-subscriber.py](example-subscriber.py) is provided as an example subscriber to mirror the publishing code.

## Tips and Tricks

- The plugin subscribes to all notifications under in the `NOTIFICATION_TYPE_NAMES` regardless of whether they are connected to ZMQ endpoints via CLI launch. For avoiding that performance overhead, entries can be dropped from the list to avoid subscribing to them.
- Unless there are changes to the plugin interfaces, notification types that are added in the future should be easy to include by adding the value to the `NOTIFICATION_TYPE_NAMES` list.
