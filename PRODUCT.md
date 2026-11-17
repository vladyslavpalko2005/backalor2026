# Backalor

<!-- impeccable:product-schema 1 -->

## Platform

Native desktop application (PyQt6), primarily macOS. This is a desktop operating surface, not a web page.

## Users

The owner is preparing a bachelor's project about digitising historical cipher keys. The working material is scanned handwritten documents, annotated manually and with local models.

## Product Purpose

Turn scans into checked hierarchical annotations and structured cipher keys, with traceable source crops and editable results.

## Operating Context

Images/PDF → preprocessing → L1 sections, L2 pairs, L3 elements → text role and element type → recognition → manual review → structured export. Ukrainian and Slovak interface. Existing local projects, annotations, recovery drafts and models must be preserved.

## Capabilities and Constraints

A server-verified Google session is mandatory before the production workspace opens. Google login registers new users automatically. The remember-login option stores its token only in an OS credential vault and verifies it again after restart; cached profile hints never authorize access. New identities are registered automatically through Google. The configured cloud API must be ready as part of application startup; normal desktop startup must not create a local backend or database; users do not enter or connect a server address inside the editor.

After login, the user explicitly chose a projects screen offering creation, opening a local project and downloading accessible server projects. Server copies are private by default, optionally public to signed-in users, or explicitly shared with reader/editor permissions. Only owners manage visibility, invitations and deletion; owners and invited editors may update versioned snapshots. Backend access checks remain authoritative. Local folders remain OS files; signing in is not filesystem encryption or a new access-control system for folders selected by the OS user.

Local ML model weights are optional and must not be fabricated or downloaded silently. JSON/COCO/YOLO export, undo/redo, recovery and project snapshots are established features. The request does not authorize deleting existing project data.

## Brand Commitments

The user rejected the previous layout and palette. Confirmed replacement direction: dark side navigation, light workspace, green action accent. The Backalor name remains. The researcher must retain room to inspect scans.

## Product Principles

- Start with one action: Google sign-in; then choose a project.
- Keep source image and editing context visible together.
- Expose frequent work directly; disclose models and precision settings when needed.
- Preserve edits through navigation, failures and authentication changes.
- Distinguish verified results from incomplete annotations and model predictions.


## November 2026 extension

The Symbols tab imports and exports portable libraries containing PNG reference crops and reviewed readable examples. Local reference matching separates readable elements from cipher symbols conservatively and abstains on weak or ambiguous matches. New handwriting still uses an explicitly selected local TrOCR model. Settings interchange includes preprocessing and model paths/thresholds, without model weights or credentials. The projects hub searches and filters all accessible documents, with pagination and owner-controlled sharing. Downloaded copies are independent files; permission revocation cannot remove existing local copies.


Cloud deployment uses managed PostgreSQL plus persistent server snapshot storage, with Docker and a Render Blueprint. PostgreSQL credentials and Google secrets stay on the server. SQLite is retained only for explicitly selected local development and old-data migration. The user has no cloud account yet; preparation is not a live deployment. Normal desktop startup requires the public API origin and never falls back to a local database.
