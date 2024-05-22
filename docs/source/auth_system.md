# Authentication and security

> :warning: **Do not use debug tools like autoreload in combination!**

The auth server and such tools are generally not compatible.
Using the auth system in a debug environment can also make it very hard to debug.

## Connecting to a server with authentication
Add or change the following line in your `config.ini` file:
```ini
USE_AUTH_SYSTEM = True
```
It is important to have the proper directory structure for the auth system to work.
If not setup yet you can use the following command to create the necessary directories:
```bash
rixaplugin setup setup-work-dir
```
This will have created an `auth_keys` folder in your work directory.

In this you will have to put your private key (`client.key_secret`) and the server's public key (`server.key`).

### RIXA webserver
Should you connect to a RIXA webserver instance, these keys can be downloaded from your account page
(Usually `https://THESERVER.com/account_managment`).

Note that your key is used on the server side for "tagging" the plugins you connect.

## Allowing others to connect to your server
The auth system needs to be activated as in above.

Keys can be generated via
```bash
rixaplugin setup generate-auth-keys NAME
```
This will generate a key pair in the `auth_keys` folder.

Note the non-optional naming conventions. A client key is named `client.key_secret` and a server key is named `server.key_secret`.

When a client connects, the name of the used public key on the server will be assigned as tag to the connected plugin/client.

### RIXA webserver
Should you use the RIXA webserver you usually do not need to worry about this.
Use the 'Plugin scopes' in the admin panel to add keys/tags.
Users can be assigned permissions to these tags. They will then be able to download the key(s) and the public server key.
