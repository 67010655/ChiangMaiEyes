# Air4Thai issuer chain

Public CA certificates downloaded from Let's Encrypt on 2026-10-13:

- https://letsencrypt.org/certs/gen-y/int-yr1.pem
  SHA-256 d5efc243446ef865c0e165eb1958a2f068c9514aa17238701bd6f7ad90253ce7
- https://letsencrypt.org/certs/gen-y/root-yr-by-x1.pem
  SHA-256 b3858d7a4d598b4ab6ed2892a1b8c0ee035154876dd40a082a3b05387eea11a4

Authority: https://letsencrypt.org/certificates/

Air4Thai HTTPS failed with `unable to get local issuer certificate` using
HTTPX's default trust bundle. These issuers complete the chain to the already
trusted ISRG Root X1. Root and hostname verification remain mandatory and
partial-chain trust is disabled. No private key, leaf pin, or additional
self-signed trust root is present. This context applies only to Air4Thai.

Check issuer rotation and expiry if the provider changes its TLS chain.
Failures still return missing concentration with composite AQI kept separate.
