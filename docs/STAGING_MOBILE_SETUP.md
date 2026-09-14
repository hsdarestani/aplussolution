# A+ Solution Mobile Staging

## Goal
A separate testing application before production releases.

## App identifiers

Production:
- Bundle/package: de.aplussolution.workforce
- Name: A+ Solution

Staging:
- Bundle/package: de.aplussolution.staging
- Name: A+ Solution Staging

## Release flow

1. Develop changes.
2. Build staging app.
3. Test with internal testers.
4. Promote the same verified changes to production.

## Required separate services

- Firebase project/app for staging
- Push notification credentials for staging
- API environment for staging
- Store listings for staging apps

Production credentials must never be used in staging builds.
