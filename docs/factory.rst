Factory App Checks
==================

Factory can implement a bounded, reviewed app issue while scheduling and
deployment remain off. The repository's ``.factory.toml`` defines portable
checks; interpreter paths, identity selectors and sandbox wrappers belong in
the operator's host configuration.

Checks and dependencies
-----------------------

Use Python 3.12 with the app requirements, documentation requirements and the
reviewed Factory build installed. Put its ``python`` and a supported Node/npm
distribution on ``PATH``. Install the Node lockfile once with ``npm ci
--ignore-scripts --no-audit --no-fund`` to populate the npm cache.

The attempt gate runs these checks in order:

* ``node-permission`` verifies that the runtime accepts the stable permission
  flag and exposes the permission model.
* ``node-dependencies`` uses ``npm ci --offline --ignore-scripts`` with audit,
  funding and log files disabled. A missing or incomplete cache fails the check;
  it does not fall back to a network install.
* ``tests`` runs the full default pytest suite. This includes actual Node
  sandbox enforcement and example deck rendering.
* ``docs`` builds Sphinx with warnings treated as errors.

Factory's conflict-marker and leak checks also run. The ``Factory app gate``
GitHub Actions workflow runs the same commands with Python 3.12 and Node 24.22.2.
Its dependency-install step warms the cache before the offline check. It has
read-only repository permissions and performs no deployment.

On a sandboxed host, expose the complete Python environment, Node distribution
and populated npm cache read-only to the check wrapper. Exposing only their
``bin`` directories is insufficient for Python packages or npm's own modules.
Set ``npm_config_cache`` in host configuration to select that cache. The worker
and checks need a writable worktree and temporary directory; they do not need
SSH keys, GitHub profiles, platform sessions or Harbor credentials. Keep the
worker model's credentials separate from the deterministic check wrapper.

State and identity boundaries
-----------------------------

Select one durable checkout as the future canonical Factory root. Before
changing roots, inventory each ``.factory`` tree and preserve checksum-verified,
private evidence archives. Compare deployment runs, approvals, acknowledgements
and incident delivery separately from ordinary lifecycle observations. An archive
is evidence, not an instruction to replay or import approvals into active state.
Do not concatenate journals or delete the old checkout as a migration shortcut.
Check the host's actual temporary-file cleanup policy before using temporary
storage for long-lived state.

The source dispatcher needs a GitHub identity that can create app branches,
issues and pull requests. Select it through host-owned
``install.dispatch_env``. Keep private platform credentials out of the source
worker and its sandbox. In the currently reviewed Factory build, apply's
identity guard also derives its account from ``install.dispatch_env`` and pins
its token. An ``apply.env.GH_CONFIG_DIR`` override alone does not establish an
independent apply identity. Do not widen apply's allowed accounts to work around
that boundary.

Deployment and scheduling remain off
------------------------------------

Repository ``apply.enabled`` is deliberately false. The proposed source-only
host profile also sets ``install.apply = false``, so rendered dispatcher units
have no apply trigger. These are independent of the systemd timer's enablement:
keep the timer disabled during onboarding, and verify both dispatcher and apply
are inactive before a bounded exercise. Rendering units with ``factory install
--print`` does not install or start them. Do not run ``factory install`` without
reviewing its effects; the normal install path enables scheduling.

The committed control bands are observation-only. Creating label definitions or
an issue template does not authorize labeling work ``ready-for-agent``. Model
triage, branch protection and the host environment must be validated separately.
If the configured triage endpoint is unavailable, leave automatic triage off;
do not treat a configured model name as proof of a working endpoint.

For the installed Factory version, ``factory dispatch --ticket N`` returns
after that issue and bypasses the general merge/sync/manager/queue pass. It
still fetches and pins the root and refuses changes outside ``.factory``.
Resolve local changes through review before running it; do not discard someone
else's edits to make the checkout appear clean. Use only a fully specified,
reviewed issue, with app gates and the real reviewer enabled. A successful local
gate is not proof that dispatcher admission, PR publication or reviewer parsing
worked end to end.

Keep human merge and separately scoped, one-at-a-time production approval.
Neither a green gate nor successful worker onboarding authorizes reconnecting
apply, starting a timer, renewing deployment sessions, or deploying an app.

Gateway models and bounded validation
-------------------------------------

Reviewed Factory supports host-owned ``triage.headers`` and
``triage.api = "anthropic"``. Set ``url`` in the triage table to the complete native
``/v1/messages`` URL (the key is ``url``, not ``endpoint``). The gateway catalog model IDs are ``Claude-Sonnet-5-5``
and ``Claude-Opus-5-5``. The existing OMP workers and reviewer also use the
native Anthropic API.

Application-key authentication requires the ``Ocp-Apim-Subscription-Key`` and
user headers. Keep them in private host configuration, never in the repository.
This example uses placeholders only:

.. code-block:: toml

   [repo."owner/name".triage]
   url = "https://gateway.example.invalid/v1/messages"
   api = "anthropic"
   model = "Claude-Sonnet-5-5"

   [repo."owner/name".triage.headers]
   Ocp-Apim-Subscription-Key = "<application-key>"
   user = "<user-header-value>"

OpenAI triage mode remains the default. The gateway's
``/api/v1/chat/completions`` answered simple Claude requests but rejected a
standard ``role=system`` message, so simple connectivity does not establish
full triage compatibility. The validated native route needs no custom
translation proxy or tunnel.

Anthropic environment variables, including ``ANTHROPIC_EXTRA_HEADERS`` and
``ANTHROPIC_CUSTOM_HEADERS``, are not automatically read by this Factory
client. Configure the explicit host-owned header table instead. The generic
``triage.key`` / ``FACTORY_LLM_KEY`` supplies ``x-api-key`` in Anthropic mode
and bearer authentication in OpenAI mode. Custom headers override these
defaults.

Bounded manual exercise
~~~~~~~~~~~~~~~~~~~~~~~

Keep the timer disabled and apply disconnected. First run ``factory triage
--issue N --dry-run``. Then obtain authorization for real triage and for the
single ``factory dispatch --ticket N`` exercise, including worker commits and
PR publication. Do not start the general service or queue. Keep human merge
and separately scoped production approval.

Current deployment guidance lives in the ``slai-app-creator`` skill, with
the complete creator asset refreshed through its supported installer. AIPPT's
existing apex route retains the platform-reviewed ``platform-apex-tls`` binding;
the application bundle carries no platform TLS ciphertext. Run the current
helper's offline validation before requesting a live deployment.

The deployment flow requires Harbor-verified digests and hosted submission. Merging an app PR alone is not
a deployment or rollout proof.
