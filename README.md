# ATLAS — ATAK Tactical Lifecycle & Administration System

Android device management for ATAK tablets: policies, applications, content,
enrolment and kiosk. Deployed as a module of
[InfraTAK](https://github.com/takwerx/infra-TAK).

By **TAK-Solutions LLC**. Licensed under the Apache License 2.0 — see `LICENSE`
and `NOTICE`.

## What this repository is

**This is a release mirror, and it carries no development history by design.**
Every tag here is a single commit with no parent: one release, one tree, nothing
to walk back through. That is deliberate rather than accidental, so please do not
expect `git log` to tell you a story.

It contains exactly what an InfraTAK deployment needs and nothing else — the
application, its migrations, the container definition, the compose file, and the
two applications an installation seeds from. The sources for the Android agent
and the ATLAS launcher are not here; the signed APKs in `dist/` are what a
deployment installs.

## Installing

Do not clone this by hand. ATLAS is installed and updated through InfraTAK's
console, which clones a tag, builds the image on the box, applies migrations and
seeds the bundled applications. Installing it any other way skips the parts that
make it work.

## Reporting something

Security reports go by email to **takwerx@gmail.com**, not to a public issue.

## Versions

`VERSION` at the root is the release, and it always equals the tag. Updates
resolve the newest tag, so the console tells a box when a newer one exists.
