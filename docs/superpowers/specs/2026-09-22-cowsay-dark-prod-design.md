# cowsay-dark prod — Design

## Overview

Bring `cowsay-dark.keld.co` up in production, sanely, and consistent with the
patterns the rest of the fleet actually uses today — `cowsay-dark` is
explicitly the template other services copy, so the pattern it demonstrates
matters as much as getting this one hostname live. Spans two repos:
`ncx-ai/cowsay` (this repo) for the k8s manifests, and `ncx-ai/infrastructure`
for the ArgoCD Application, the prod-deploy gate, and the DNS record.

Verified against the live repos rather than assumed:

- `cowsay` prod's own Ingress is still pulumi-created in
  `infrastructure/pulumi/__main__.py`, with a comment noting dev already
  migrated to being self-owned in the app repo (applied by ArgoCD) and "prod
  has not been migrated yet."
- `ncx-ai/api-gateway` already runs the self-owned-Ingress pattern for BOTH
  its dev *and* prd overlays (`k8s/api-gateway/overlays/{dev,prd}/ingress.yaml`,
  both using the same `_components/ingress` Component cowsay's dev overlay
  uses). Its `_components/ingress/kustomization.yaml` says outright: "Copied
  verbatim from ncx-ai/cowsay so the two repos stay comparable."
- `infrastructure/docs/superpowers/specs/2026-09-17-keld-website-migration-design.md`
  names `ncx-ai/cowsay` + the generic `deploy.yml`/`deploy-dev.yml` pipeline as
  the platform's reference pattern for a new service, explicitly *not*
  `deploy-atlas{,-dev}.yml` (atlas is a deliberate outlier: dedicated
  per-service workflow, manifest_sha pinning, its own smoke-test job, Helm
  charts instead of kustomize).

So: self-owned Ingress in `ncx-ai/cowsay`, applied by ArgoCD, is the pattern
to build on — not `cowsay` prod's own legacy pulumi-managed Ingress.

## What already exists (no change needed)

- The shared `cowsay-cloudflare-only` Cloud Armor policy/BackendConfig covers
  `cowsay-dark` already — its Service (`k8s/cowsay-dark/base/service.yaml`)
  already carries the `cloud.google.com/backend-config` annotation (commit
  `5019d01`), deliberately sharing `cowsay`'s policy rather than getting its
  own (same app, two flavors, one origin — see that commit's message).
- A Cloudflare Access application for `cowsay-dark.keld.co` already exists in
  `infrastructure/pulumi/cloudflare/access.py` (slug `cowsay-dark`, policy
  `allow-team-keld-co`), imported from real Cloudflare state on 2026-09-09.
- cert-manager and the `letsencrypt-cloudflare` ClusterIssuer are cluster-wide
  singletons already created on the prod cluster.
- The `cowsay` namespace and its `cowsay-secrets` Secret (holding
  `DATABASE_URL`) already exist in prod, created by `cowsay`'s own deploys.
  `cowsay-dark`'s Deployment already references the same secret name and
  lands in the same namespace, so it needs no secret injection of its own.

## Changes: `ncx-ai/cowsay`

### 1. Fix `cowsay-dark`'s base — prod-ingress-leak bug

`k8s/cowsay-dark/base/kustomization.yaml` still bundles `ingress.yaml` (baked
with the *dev* hostname `cowsay-dark-dev.keld.co` and TLS secret
`cowsay-dark-dev-tls`) and the `_components/ingress` Component into the
shared base. This is the identical leak `bba5989` fixed for plain `cowsay`
(`k8s/cowsay/base/`) — noted at the time as deliberately out of scope for
that PR ("cowsay-dark's dev overlay (independent base/ingress.yaml) is
unaffected"). Since the new prod overlay below also composes `base`, this has
to be fixed first, or a `kubectl kustomize` of prod would render (or, if
kustomize's duplicate-resource-ID check fires first, outright fail on) the
dev Ingress.

Fix, mirroring `bba5989` exactly:

- `git mv k8s/cowsay-dark/base/ingress.yaml k8s/cowsay-dark/overlays/dev/ingress.yaml`
- Remove `ingress.yaml` and the `_components/ingress` Component from
  `k8s/cowsay-dark/base/kustomization.yaml`.
- Add both to `k8s/cowsay-dark/overlays/dev/kustomization.yaml` (component
  path one level deeper than base's: `../../../_components/ingress`).
- Verify: `kubectl kustomize k8s/cowsay-dark/overlays/dev` renders
  byte-identical before/after.

### 2. Add `k8s/cowsay-dark/overlays/prd/`

- **`kustomization.yaml`**: `_components/ingress` Component; resources
  `../../base` + `ingress.yaml`; `namespace: cowsay`; image pinned to
  `5d3ddc63ef19b33bc52c7ea46bb20e39de3d952e` — today's actual `cowsay` prod
  tag, not the dev overlay's older pin, so prod `cowsay-dark` runs a build
  that's actually been validated in prod. No resource patch (dev's
  cpu/memory-shrink patch is dev-only; prod keeps base's request/limit
  values, matching how `cowsay` prod keeps base's).
- **`ingress.yaml`**: host `cowsay-dark.keld.co`, TLS secret
  `cowsay-dark-tls`, backend `cowsay-dark:80`. Ephemeral GKE IP (no
  `global-static-ip-name` annotation) — matches `cowsay` prod's own Ingress,
  per your call to stay consistent with `cowsay` rather than adopt
  `api-gateway`'s newer static-IP pattern.
- No CI change: `ci.yml` only ever touches `k8s/cowsay/overlays/*`, and
  `cowsay-dark`'s tag stays manually pinned in both overlays, matching how
  dev already works (see the existing comment in
  `overlays/dev/kustomization.yaml`).

### Testing

- `kubectl kustomize k8s/cowsay-dark/overlays/prd` renders Service + Deployment
  + Ingress (base's Service/Deployment plus the new Ingress) with the right
  hostname/tag/namespace, and no stray dev hostname anywhere in it. The
  Service has to be there — the Ingress routes to it, and it's what carries
  the Cloud Armor `backend-config` annotation.
- `kubectl kustomize k8s/cowsay-dark/overlays/dev` unchanged from before the
  base fix (diff against current output produces nothing).
- `./venv/bin/python -m pytest` (or this repo's equivalent) still passes —
  this change touches only `k8s/`, no app code.

## Changes: `ncx-ai/infrastructure` (separate repo, separate branch/PR, same
branch name: `skyler/cowsay-dark-prod-setup-43250c`)

### 3. `argocd/cowsay-dark-app.yaml`

New static ArgoCD Application, mirroring `argocd/cowsay-app.yaml` exactly
(not an ApplicationSet — prod uses one static file per app-flavor, unlike
dev's `cowsay-appset.yaml`, which is dev-only machinery for auto-discovering
`k8s/*/overlays/dev`):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: cowsay-dark
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/ncx-ai/cowsay
    targetRevision: main
    path: k8s/cowsay-dark/overlays/prd
  destination:
    server: https://kubernetes.default.svc
    namespace: cowsay
  syncPolicy:
    syncOptions:
      - CreateNamespace=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
```

`name: cowsay-dark` is load-bearing, not tidy: `deploy.yml` runs
`argocd app sync ${{ env.SERVICE }}`, so a prod deploy dispatch with
`service: cowsay-dark` needs an Application of exactly that name to exist.

### 4. `prod-deploy.yaml`

Add:

```yaml
  cowsay-dark:
    loadtest_gated: false
    approvers: [dshore, awskylershepard]
```

Same approvers as `cowsay` (same team, same app). Per this file's own
checklist ("Adding a service here is the LAST step"), this only lands after
#3 above and the `cowsay-dark` prod overlay both exist.

### 5. `pulumi/cloudflare/dns.py` — NOT part of the infra PR; a manual follow-up

Verified against `pulumi/cloudflare/tests/test_program.py` and
`.github/workflows/checks.yml`: the `cloudflare` CI job runs on **every** PR
to this repo, unconditionally (no path filter), and
`test_no_record_carries_a_placeholder_address` matches one specific literal
sentinel (`RESERVED-IP-PENDING-TASK-4-APPLY`) — precisely, not any
placeholder-shaped string. So a `cowsay-dark-a` row using that exact,
repo-approved sentinel fails CI for this PR and (since the job isn't scoped
to `pulumi/cloudflare/**`) every other PR touching this repo, by design,
until someone fixes it. A row using any *other* made-up value (`0.0.0.0`,
`TODO`, etc.) would **not** be caught by this test — it would pass CI and
silently apply a wrong DNS record, which is worse. Either way, no invented
value belongs in the merged PR.

So `dns.py` gets **no change in the infra PR at all**. The record is added
in a follow-up, once the real address is known — directly with the real IP,
never a placeholder, and **as a small PR, not a direct commit to main**
(this repo gates every PR through `checks.yml`; a direct commit skips that
gate entirely, which is the opposite of the caution this section is
otherwise taking):

```python
Record(slug="cowsay-dark-a", name="cowsay-dark.keld.co", type="A", ttl=1, content="<real ephemeral GCLB IP>", proxied=True),
```

placed alphabetically between the existing `cowsay-dark-dev-a` and
`cowsay-dev-a` rows. **This PR must also bump
`pulumi/cloudflare/tests/test_program.py`'s `EXPECTED["records"]` from `47`
to `48` in the same commit** — `test_program_constructs_every_resource`
counts `dns.RECORDS` against that literal, and the two rows (data + count)
have to land together or this follow-up PR's own CI fails on arrival, which
is exactly the kind of red-CI-on-merge mistake this section already worked
to avoid for the main PR.

The IP value itself is exactly how `cowsay-prod-a`'s content
(`8.233.146.154`) was originally populated — there's no way to know it ahead
of a real deploy, and nothing in this session can produce it (no
cluster/cloud credentials here). See Sequencing step 3 below for the exact
commands.

## Sequencing (cross-repo, has to happen in this order)

1. Land and merge the `ncx-ai/cowsay` PR (fixes #1 + adds #2 above).
2. Land the `ncx-ai/infrastructure` PR (#3 + #4 only — no `dns.py` change).
3. A human with cluster/cloud credentials (this session has neither):
   a. Manually trigger `ncx-ai/infrastructure`'s `deploy.yml`
      (`workflow_dispatch`, `service: cowsay-dark`, `sha:
      5d3ddc63ef19b33bc52c7ea46bb20e39de3d952e`) — or via
      `repository_dispatch` the same way `cowsay`'s CI does it.
   b. Approving the manual-approval gate syncs the `cowsay-dark` Application
      (already created by app-of-apps on merge), which creates the Ingress
      object. **This sync will likely report failed/timed-out the first
      time**: `deploy.yml` gives the app 300s to reach `Healthy`, ArgoCD only
      considers a `networking.k8s.io/Ingress` Healthy once it has an address
      (`status.loadBalancer.ingress`), and steps c–d below can easily take
      longer than 300s combined. That's expected, not a real failure — it
      also means the "Update registry" step won't run on this first attempt,
      so `registry/cowsay-dark.yaml` won't be written yet. Re-run the sync
      (`argocd app sync cowsay-dark` / re-dispatch) once step d has actually
      finished, so the health wait has something to succeed against and the
      registry gets its entry.
   c. cert-manager's ingress-shim sees the Ingress's `cluster-issuer`
      annotation and creates a Certificate, which completes a DNS-01
      challenge against Cloudflare — this only needs the `_acme-challenge`
      TXT record cert-manager creates itself via the Cloudflare API token,
      **not** the `cowsay-dark-a` record; the two are independent.
   d. Once that challenge completes, the `cowsay-dark-tls` secret is
      populated. Only then does GKE's ingress controller provision the GCLB
      and assign it an ephemeral IP — per `pulumi/__main__.py`'s own comment,
      it "won't provision the load balancer at all... until the TLS secret
      the Ingress references actually exists." So there's a real wait here
      before an IP exists to read.
   e. `kubectl get ingress -n cowsay cowsay-dark` to read the assigned IP,
      then add the `cowsay-dark-a` row (with the `EXPECTED["records"]` bump
      in the same commit — see section 5 above) to `dns.py` with that real
      IP, as its own small PR, then `pulumi up` once it merges.
   f. Verify: `curl -I https://cowsay-dark.keld.co` redirects to Cloudflare
      Access login; `curl -H "Host: cowsay-dark.keld.co" https://<GCLB IP>/`
      is refused (Cloud Armor policy holding, matching the check `5019d01`
      already ran for `cowsay-dev`/`cowsay-prod`).

Steps 3a–3f are **out of scope for this session** — no cloud credentials are
available here — and are called out explicitly rather than silently skipped
so nothing gets marked done that isn't.

## Non-goals

- Not touching `cowsay` (non-dark) prod's existing pulumi-managed Ingress —
  migrating it to the self-owned pattern is a separate, larger change (it has
  real traffic) and isn't this task.
- Not adding a static IP for `cowsay-dark` — explicitly declined in favor of
  matching `cowsay` prod's existing ephemeral-IP behavior. **This match is
  not exact, and the difference matters more here than it does for `cowsay`
  itself**: `cowsay` prod's Ingress is pulumi-created and never pruned by
  ArgoCD, so its ephemeral IP is stable in practice even though nothing
  reserves it. `cowsay-dark`'s Ingress is ArgoCD-owned, with a cascade
  finalizer and `prune: true` on app-of-apps — so deleting or renaming
  `argocd/cowsay-dark-app.yaml`, or an ArgoCD-driven recreate of the Ingress,
  *can* release the IP while `cowsay-dark-a` still points at it, silently
  breaking the hostname until someone notices and re-points DNS. `atlas`'s
  and `api-gateway`'s own Ingresses avoid exactly this by using a
  pulumi-reserved static IP instead. Accepted here as a real, if unlikely,
  trade-off for staying consistent with `cowsay`'s current setup — flagged
  explicitly rather than silently carried, since reversing it later means
  adding a `create_static_ip()` call in `pulumi/__main__.py` and switching
  the DNS row from a hand-filled value to that reserved address.
- Not building CI automation to keep `cowsay-dark`'s prod tag in sync with
  `cowsay`'s — matches the existing manual-pin convention for this app.
