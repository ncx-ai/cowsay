# cowsay-dark prod (cowsay repo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `cowsay-dark` a working prod k8s overlay in this repo (`ncx-ai/cowsay`) — fixing the pre-existing base/ingress leak first — so `ncx-ai/infrastructure`'s new ArgoCD Application has something correct to sync.

**Architecture:** Two independent, self-contained changes to `k8s/cowsay-dark/`: (1) move the dev-only `Ingress` out of `base/` into `overlays/dev/`, mirroring the fix already applied to plain `cowsay` in commit `bba5989`; (2) add a new `overlays/prd/` composing the now-clean `base/` with its own prod `Ingress`. No application code changes, no CI changes.

**Tech Stack:** Kustomize (`kubectl kustomize`), no new dependencies.

**Spec:** [docs/superpowers/specs/2026-09-22-cowsay-dark-prod-design.md](../specs/2026-09-22-cowsay-dark-prod-design.md)

**Companion plan:** `ncx-ai/infrastructure`'s `docs/superpowers/plans/2026-09-22-cowsay-dark-prod-infra-repo.md`, same branch name (`skyler/cowsay-dark-prod-setup-43250c`) — the ArgoCD Application, `prod-deploy.yaml` gate. Independent of this plan (separate repo, separate PR); either can execute first, but neither is useful in prod without the other.

## Global Constraints

- Prod image tag: `5d3ddc63ef19b33bc52c7ea46bb20e39de3d952e` (today's `cowsay` prod tag — same image, `UI_MODE=dark`), pinned manually. Never let CI touch `k8s/cowsay-dark/*` — `ci.yml` only touches `k8s/cowsay/overlays/*`, and that must stay true.
- Prod hostname: `cowsay-dark.keld.co`. Prod TLS secret name: `cowsay-dark-tls`.
- Ephemeral GKE IP only — no `kubernetes.io/ingress.global-static-ip-name` annotation on the prod `Ingress`.
- Every kustomize change is verified by actually running `kubectl kustomize` and inspecting the rendered output — this repo has no manifest-level pytest suite, so that rendered-output check *is* the test for this plan (matching how `bba5989`'s own PR description verified itself).

---

## Task 1: Fix `cowsay-dark`'s base/ingress leak

`k8s/cowsay-dark/base/kustomization.yaml` currently bundles `ingress.yaml` (the *dev* hostname/TLS secret) and the `_components/ingress` Component into the shared base. Any overlay that composes this base — including the prod overlay Task 2 adds — would render that dev Ingress too. `bba5989` fixed the identical bug for plain `cowsay` by moving `ingress.yaml` into `overlays/dev/`; this task does the same move for `cowsay-dark`.

**Files:**
- Move: `k8s/cowsay-dark/base/ingress.yaml` → `k8s/cowsay-dark/overlays/dev/ingress.yaml` (content unchanged)
- Modify: `k8s/cowsay-dark/base/kustomization.yaml`
- Modify: `k8s/cowsay-dark/overlays/dev/kustomization.yaml`

**Interfaces:**
- Produces: a `k8s/cowsay-dark/base/` that renders only `Deployment` + `Service` (no `Ingress`) — Task 2 depends on this being true before it adds its own `Ingress` under the same resource name.

- [ ] **Step 1: Capture the current dev-overlay render as a baseline**

```bash
kubectl kustomize k8s/cowsay-dark/overlays/dev > /tmp/cowsay-dark-dev-before.yaml
```

- [ ] **Step 2: Move the Ingress file**

```bash
git mv k8s/cowsay-dark/base/ingress.yaml k8s/cowsay-dark/overlays/dev/ingress.yaml
```

- [ ] **Step 3: Strip the Ingress and its Component from base**

Edit `k8s/cowsay-dark/base/kustomization.yaml` to:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
```

- [ ] **Step 4: Add the Ingress and its Component to the dev overlay**

Edit `k8s/cowsay-dark/overlays/dev/kustomization.yaml` to (only the `components:` block and `ingress.yaml` resource line are new — everything else is unchanged from the current file):

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
components:
  - ../../../_components/ingress
resources:
  - ../../base
  - ingress.yaml
namespace: cowsay
images:
  - name: cowsay
    # Replace YOUR_ARTIFACT_REGISTRY_URL with the real Artifact Registry URL
    # once (see ncx-ai/infrastructure's README).
    # Pinned manually -- ci.yml does NOT update this app's tag (it only touches
    # k8s/cowsay/overlays/*). Bump by hand to move cowsay-dark onto a newer image.
    newName: us-east1-docker.pkg.dev/ncx-ai-prod/ncx/cowsay
    newTag: d1e4be22b2061c177d88599066178ee2442346cf
patches:
  - target:
      kind: Deployment
      name: cowsay-dark
    patch: |-
      - op: replace
        path: /spec/template/spec/containers/0/resources
        value:
          requests:
            cpu: 50m
            memory: 64Mi
          limits:
            cpu: 100m
            memory: 128Mi
```

(The component path is `../../../_components/ingress`, one level deeper than base's old `../../_components/ingress`, because `overlays/dev/` sits one directory deeper than `base/`.)

- [ ] **Step 5: Verify the dev render is byte-identical**

```bash
kubectl kustomize k8s/cowsay-dark/overlays/dev > /tmp/cowsay-dark-dev-after.yaml
diff /tmp/cowsay-dark-dev-before.yaml /tmp/cowsay-dark-dev-after.yaml
```

Expected: no output (files identical). If this diffs, stop and find out why before continuing — the whole point of this task is that dev's behavior does not change.

- [ ] **Step 6: Verify base no longer renders an Ingress**

```bash
kubectl kustomize k8s/cowsay-dark/base
```

Expected: two documents only (`Service` and `Deployment`), no `kind: Ingress` anywhere in the output.

- [ ] **Step 7: Commit**

```bash
git add k8s/cowsay-dark/base/kustomization.yaml k8s/cowsay-dark/overlays/dev/kustomization.yaml k8s/cowsay-dark/overlays/dev/ingress.yaml
git commit -m "Fix cowsay-dark's prod-ingress leak: move dev-only Ingress out of shared base

Mirrors bba5989, which fixed the identical bug for plain cowsay.
k8s/cowsay-dark/base/kustomization.yaml bundled ingress.yaml (the dev
hostname/TLS secret) into the shared base, so any future prod overlay
composing base would leak cowsay-dark-dev.keld.co. Moved into
overlays/dev/ instead, verified byte-identical.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: Add `k8s/cowsay-dark/overlays/prd/`

**Files:**
- Create: `k8s/cowsay-dark/overlays/prd/ingress.yaml`
- Create: `k8s/cowsay-dark/overlays/prd/kustomization.yaml`

**Interfaces:**
- Consumes: `k8s/cowsay-dark/base/` (Task 1's cleaned-up base — `Deployment` + `Service` only) and `k8s/_components/ingress/` (the shared cert-manager/GKE annotation Component, unchanged).
- Produces: a `k8s/cowsay-dark/overlays/prd` path that `ncx-ai/infrastructure`'s new `argocd/cowsay-dark-app.yaml` (separate repo, separate plan) will point ArgoCD at.

- [ ] **Step 1: Create the prod Ingress**

Create `k8s/cowsay-dark/overlays/prd/ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: cowsay-dark
spec:
  tls:
    - hosts:
        - cowsay-dark.keld.co
      secretName: cowsay-dark-tls
  rules:
    - host: cowsay-dark.keld.co
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: cowsay-dark
                port:
                  number: 80
```

- [ ] **Step 2: Create the prod kustomization**

Create `k8s/cowsay-dark/overlays/prd/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
components:
  - ../../../_components/ingress
resources:
  - ../../base
  - ingress.yaml
namespace: cowsay
images:
  - name: cowsay
    # Replace YOUR_ARTIFACT_REGISTRY_URL with the real Artifact Registry URL
    # once (see ncx-ai/infrastructure's README).
    # Pinned manually -- ci.yml does NOT update this app's tag (it only touches
    # k8s/cowsay/overlays/*). Bump by hand to move cowsay-dark onto a newer image.
    newName: us-east1-docker.pkg.dev/ncx-ai-prod/ncx/cowsay
    newTag: 5d3ddc63ef19b33bc52c7ea46bb20e39de3d952e
```

No `patches:` block — unlike dev, prod keeps base's request/limit values as-is, matching how plain `cowsay`'s prod overlay keeps base's.

- [ ] **Step 3: Render and inspect**

```bash
kubectl kustomize k8s/cowsay-dark/overlays/prd
```

Expected: three documents —

- `Service` named `cowsay-dark`, namespace `cowsay`, carrying the `cloud.google.com/backend-config: '{"default": "cowsay-cloudflare-only"}'` annotation (inherited from base).
- `Deployment` named `cowsay-dark`, namespace `cowsay`, image
  `us-east1-docker.pkg.dev/ncx-ai-prod/ncx/cowsay:5d3ddc63ef19b33bc52c7ea46bb20e39de3d952e`,
  env `UI_MODE=dark`, **no** resource-request/limit override (base's `100m/128Mi` request,
  `250m/256Mi` limit).
- `Ingress` named `cowsay-dark`, namespace `cowsay`, annotations
  `cert-manager.io/cluster-issuer: letsencrypt-cloudflare` and
  `kubernetes.io/ingress.class: gce`, host `cowsay-dark.keld.co`, TLS secret
  `cowsay-dark-tls`, no `global-static-ip-name` annotation.

- [ ] **Step 4: Verify no dev hostname leaked in**

```bash
kubectl kustomize k8s/cowsay-dark/overlays/prd | grep -c "cowsay-dark-dev" || echo 0
```

Expected: `0`.

- [ ] **Step 5: Verify dev overlay is still unaffected**

```bash
kubectl kustomize k8s/cowsay-dark/overlays/dev > /tmp/cowsay-dark-dev-after-task2.yaml
diff /tmp/cowsay-dark-dev-after.yaml /tmp/cowsay-dark-dev-after-task2.yaml
```

Expected: no output — adding the prod overlay must not change dev's render at all.

- [ ] **Step 6: Commit**

```bash
git add k8s/cowsay-dark/overlays/prd/
git commit -m "Add cowsay-dark prod overlay

k8s/cowsay-dark/overlays/prd/: cowsay-dark.keld.co, ephemeral GKE IP
(matching cowsay prod's own Ingress), pinned to cowsay prod's current
image tag. Depends on the base/ingress-leak fix in the prior commit.

Companion PR in ncx-ai/infrastructure (same branch name) adds the
ArgoCD Application, prod-deploy.yaml gate, and DNS record needed to
actually deploy this.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-Review Notes

- **Spec coverage:** Task 1 covers spec section "1. Fix `cowsay-dark`'s base — prod-ingress-leak bug." Task 2 covers spec section "2. Add `k8s/cowsay-dark/overlays/prd/`." The spec's infra-repo sections (3–5) and cross-repo sequencing are out of scope for this plan by design — see the companion `ncx-ai/infrastructure` plan.
- **Placeholder scan:** none — every step has literal file content and literal expected command output, verified against a real `kubectl kustomize` render during planning (not guessed).
- **Type consistency:** N/A (no code, only YAML manifests); resource/namespace/hostname names cross-checked against the spec and against the actual rendered output above.
