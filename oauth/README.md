# SolarEdge Site Access (OAuth)

This standalone application authenticates a SolarEdge Site Access application
and displays the received token response once in the browser. It does not store
tokens or refresh them automatically.

This entire subproject was created by AI (GPT-6 Luna)!

## Prerequisites

- A Site Access application registered in the [SolarEdge Developer
  Portal](https://developer.solaredge.com/), with a client ID, client secret,
  and the `SITE_DATA` permission.
- The redirect URI `https://helios.example.com/oauth/callback` must be
  registered with SolarEdge exactly as shown and reachable from the browser.
  An HTTPS reverse proxy must forward `/oauth/` to the container unchanged.
- Docker and a secure environment for the credentials.

## Configuration

Create a file outside the build context, for example
`$HOME/solaredge-oauth.env`, and protect it with `chmod 600`:

```text
SOLAREDGE_CLIENT_ID=Client-ID
SOLAREDGE_CLIENT_SECRET=Client-Secret
SOLAREDGE_REDIRECT_URI=https://helios.example.com/oauth/callback
FLASK_SECRET_KEY=Random-secret-value-at-least-32-characters-long
```

Generate a unique random value for `FLASK_SECRET_KEY`, for example with
`openssl rand -hex 32`. Do not commit or share the file.

## Start with Docker Compose and Traefik

Traefik v3 must use the Docker provider and be connected to the existing
external Docker network. The Compose file expects the network `traefik`, the
HTTPS entrypoint `websecure`, and the certificate resolver `letsencrypt`
already configured in Traefik. If your names differ, set the corresponding
variables before starting:

```sh
export TRAEFIK_NETWORK=traefik
export TRAEFIK_ENTRYPOINT=websecure
export TRAEFIK_CERT_RESOLVER=letsencrypt
# Optional, if the credentials file is in a different location:
export SOLAREDGE_ENV_FILE="$HOME/solaredge-oauth.env"
docker compose up -d --build
```

The container does not publish a host port. Traefik forwards
`https://helios.example-com/oauth/` and all paths below it unchanged to port
5000 in the container. DNS and the HTTPS certificate must be configured
accordingly. Stop the application with `docker compose down`.

The router labels disable Traefik access logs and tracing for this application.
All upstream proxies and other logs must also be configured not to log callback
query parameters. The application does not secure access itself; make it
available only to trusted people.

## Alternative: Start without Compose

```sh
docker build -t solaredge-oauth .
docker run --rm -p 127.0.0.1:5000:5000 \
  --env-file "$HOME/solaredge-oauth.env" solaredge-oauth
```

Open `https://helios.example.com/oauth/` in a browser and sign in. The reverse
proxy must forward `/oauth/`, including `/oauth/callback`, to port 5000 without
removing the prefix. Then store the displayed tokens securely and persistently.
Anyone who has the tokens can access the authorized site. The application is
not secured for public or shared access. A trusted HTTPS reverse proxy must
protect access; in particular, its logs must not include callback query
parameters.

For local testing, you can instead configure `http://localhost:5000/callback`
as the redirect URI and open `http://localhost:5000/`. This address must also
be registered with SolarEdge; whether local HTTP addresses are allowed depends
on the portal requirements.

Access tokens expire; refresh tokens are replaced when refreshed, and the new
token must be saved. This application does not handle token refresh or
integration with Helios.

SolarEdge: [Authentication](https://api-docs.solaredge.com/docs/developer-platform/g09jmvp5t2cok-authentication).
