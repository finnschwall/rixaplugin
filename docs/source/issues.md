# Plugin programming quickstart

* Max hops for calls (prevent circular calls)
* truncated call stack for exceptions (remove rixaplugin.internal when debug is off)
* propagating timeout

* job tracker for each plugin
* add export function so that plugins can be called even when not connected yet (add ZMQ curve to plugconf)
* add option for remotes to just signal being alive instead of sending data
* add option to connect without sending any data (plugconfs)
* add option to connect without receiving any data (plugconfs)