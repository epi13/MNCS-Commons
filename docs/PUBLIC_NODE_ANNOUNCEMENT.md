# Experimental public-node announcement notes

Publish an announcement only after an operator has deployed and verified a real
endpoint. Replace `<hostname>`; this repository does not claim that a public node
is currently live.

The announcement should include:

- `https://<hostname>/.well-known/mncs-commons` for machine discovery;
- the [Commons repository](https://github.com/epi13/MNCS-Commons);
- a statement that contributions are public, bounded, untrusted information;
- a request for independent PASS/FAIL/UNKNOWN interoperability reports;
- a warning not to submit secrets, credentials, private data, or unrestricted
  exploit material;
- the fact that participant identity is self-asserted and publication grants no
  authority;
- the read-only emergency procedure and an operator contact for abuse reports.

The first useful contributions are small client implementations, ambiguity
reports, failed replications, and scope-limited observations. A WorkRequest is
not a command and the node never dispatches Forge, Fabric, shell, Git, or network
work from record contents.
