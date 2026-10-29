"use strict";

if (new URLSearchParams(globalThis.location.search).has("capture")) {
  document.body.classList.add("publication-capture");
}

const datasets = {
  synthetic: { label: "Synthetic planted cycles", path: "../results/evaluation_corpora/synthetic.json" },
  glassdoor_simplyhired_jobs: { label: "Glassdoor and SimplyHired jobs, all 18,870 rows", path: "../results/evaluation_corpora/glassdoor_simplyhired_jobs.json" },
  glassdoor_simplyhired_jobs_unique_descriptions: { label: "Glassdoor and SimplyHired jobs, 5,317 unique descriptions", path: "../results/evaluation_corpora/glassdoor_simplyhired_jobs_unique_descriptions.json" },
  onet_500: { label: "O*NET 30.3, first 500 occupations", path: "../results/evaluation_corpora/onet_500.json" },
  acmart: { label: "ACM template corpus", path: "../results/evaluation_corpora/acmart.json" },
  python_stdlib_100: { label: "Python standard library, first 100 files", path: "../results/evaluation_corpora/python_stdlib_100.json" }
};

const elements = Object.fromEntries([
  "corpus-select", "confidence", "confidence-output", "lift", "lift-output",
  "relation-select", "claim-select", "search", "status", "component-list", "component-count",
  "graph-view", "detail-content", "comparison-content", "edge-table", "edge-count",
  "configuration-note", "export-button", "manifest-button", "certificate-panel",
  "validation-count", "walkthrough-content"
].map((id) => [id, document.getElementById(id)]));

let analysis = null;
let current = null;
let externalValidation = null;

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;"
  }[character]));
}

function stronglyConnectedComponents(nodes, edges) {
  const adjacency = new Map(nodes.map((node) => [node, []]));
  edges.forEach((edge) => adjacency.get(edge.source)?.push(edge.target));
  const indices = new Map();
  const lowLinks = new Map();
  const stack = [];
  const onStack = new Set();
  const components = [];
  let index = 0;

  function visit(node) {
    indices.set(node, index);
    lowLinks.set(node, index);
    index += 1;
    stack.push(node);
    onStack.add(node);
    for (const target of adjacency.get(node) || []) {
      if (!indices.has(target)) {
        visit(target);
        lowLinks.set(node, Math.min(lowLinks.get(node), lowLinks.get(target)));
      } else if (onStack.has(target)) {
        lowLinks.set(node, Math.min(lowLinks.get(node), indices.get(target)));
      }
    }
    if (lowLinks.get(node) === indices.get(node)) {
      const component = [];
      let member;
      do {
        member = stack.pop();
        onStack.delete(member);
        component.push(member);
      } while (member !== node);
      components.push(component.sort());
    }
  }

  nodes.forEach((node) => { if (!indices.has(node)) visit(node); });
  return components.sort((left, right) => right.length - left.length || left[0].localeCompare(right[0]));
}

function weakComponents(nodes, edges) {
  const adjacency = new Map(nodes.map((node) => [node, new Set()]));
  edges.forEach(({ source, target }) => {
    adjacency.get(source)?.add(target);
    adjacency.get(target)?.add(source);
  });
  const seen = new Set();
  const groups = [];
  for (const node of nodes) {
    if (seen.has(node)) continue;
    const group = [];
    const pending = [node];
    seen.add(node);
    while (pending.length) {
      const member = pending.pop();
      group.push(member);
      for (const neighbor of adjacency.get(member)) {
        if (!seen.has(neighbor)) {
          seen.add(neighbor);
          pending.push(neighbor);
        }
      }
    }
    groups.push(group);
  }
  return groups
    .map((group) => group.sort())
    .sort((left, right) => right.length - left.length || left[0].localeCompare(right[0]));
}

function requireCertificate(certificate) {
  const required = ["policy_version", "claim_type", "decision", "allowed_encoding", "allowed_statement", "allowed_export", "requested_representation_authorized", "witness"];
  if (!certificate || required.some((field) => !(field in certificate))) throw new Error("requested semantic output lacks a valid certificate");
  const decisions = new Set(["ADMIT", "QUALIFY", "REFUSE"]);
  const encodings = new Set(["undirected-link", "conditional-asymmetry-glyph", "directed-arrow", "contested-relation", "no-relation"]);
  if (!decisions.has(certificate.decision) || !encodings.has(certificate.allowed_encoding) || !certificate.allowed_statement) throw new Error("certificate output authorization is malformed");
  if (certificate.decision === "REFUSE" && (certificate.allowed_export || certificate.requested_representation_authorized || certificate.allowed_encoding === "directed-arrow")) throw new Error("refused certificate authorizes semantic output");
  if (certificate.allowed_encoding === "directed-arrow" && certificate.decision !== "ADMIT") throw new Error("semantic arrow lacks admission");
  return certificate;
}

function selectedCertificate() {
  const matches = analysis.claim_certificates.filter((item) => item.claim_type === elements["claim-select"].value);
  if (matches.length !== 1) throw new Error(`expected one certificate for ${elements["claim-select"].value}`);
  return requireCertificate(matches[0]);
}

function undirectedEdges(edges) {
  const seen = new Set();
  return edges.filter((edge) => {
    const key = [edge.source, edge.target].sort().join("\u0000");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function deriveState() {
  const confidence = Number(elements.confidence.value);
  const lift = Number(elements.lift.value);
  const relation = elements["relation-select"].value;
  const requestedEdges = analysis.edges.filter((edge) =>
    edge.confidence >= confidence && edge.lift >= lift &&
    (relation === "all" || edge.relation_type === relation)
  );
  const certificate = selectedCertificate();
  const encoding = certificate.allowed_encoding;
  const semanticDirected = encoding === "directed-arrow";
  const conditionalAsymmetry = encoding === "conditional-asymmetry-glyph";
  const contested = encoding === "contested-relation";
  const noRelation = encoding === "no-relation";
  const directed = semanticDirected || conditionalAsymmetry || contested;
  const edges = noRelation ? [] :
    encoding === "undirected-link" ? undirectedEdges(requestedEdges) : requestedEdges;
  const components = directed ?
    stronglyConnectedComponents(analysis.nodes, edges) : weakComponents(analysis.nodes, edges);
  const membership = new Map();
  components.forEach((component, index) => component.forEach((node) => membership.set(node, index)));
  const condensation = new Set();
  if (directed) edges.forEach(({ source, target }) => {
    const left = membership.get(source);
    const right = membership.get(target);
    if (left !== right) condensation.add(`${left}:${right}`);
  });
  current = {
    confidence, lift, relation, edges, requestedEdges, components, membership,
    condensation, weak: weakComponents(analysis.nodes, edges), certificate, directed,
    semanticDirected, conditionalAsymmetry, contested, noRelation
  };
}

function renderMetrics() {
  const nontrivial = current.components.filter((component) => component.length > 1);
  const values = {
    documents: analysis.document_count,
    edges: current.edges.length,
    sccs: current.components.length,
    nontrivial: nontrivial.length,
    largest: current.components[0]?.length || 0,
    weak: current.weak.length,
    singletons: analysis.nodes.length
  };
  Object.entries(values).forEach(([key, value]) => {
    document.getElementById(`metric-${key}`).textContent = value.toLocaleString();
  });
  document.getElementById("metric-sccs-label").textContent = current.noRelation ? "Singletons" : current.conditionalAsymmetry ? "Conditional SCCs" : current.directed ? "Semantic SCCs" : "Association groups";
  document.getElementById("metric-nontrivial-label").textContent = current.directed ? "Nontrivial SCCs" : "Nontrivial groups";
  document.getElementById("metric-largest-label").textContent = current.directed ? "Largest SCC" : "Largest group";
}

// certificate-guarded-output-entry-point: inspector statement rendering; guard=requireCertificate
function renderCertificate() {
  requireCertificate(current.certificate);
  const certificate = current.certificate;
  const required = certificate.required_predicates?.length ?
    certificate.required_predicates.map((predicate) => predicate.description).join(" OR ") :
    certificate.required_alternatives.map((alternative) => alternative.join(" + ")).join(" OR ");
  const fallback = certificate.fallback_claim ? certificate.fallback_claim.replaceAll("-", " ") : "None required";
  const counterevidence = certificate.counterevidence?.length ? certificate.counterevidence.join("; ") : "none recorded";
  const survival = certificate.specification_survival == null ? "not evaluated" :
    `${Number(certificate.specification_survival).toFixed(3)} (${certificate.decision === "QUALIFY" ? "typed qualification" : "reported value"})`;
  const exportStatus = certificate.allowed_export ? "requested claim exportable" :
    certificate.fallback_claim ? "requested claim blocked; fallback only" : "blocked";
  const requiredObjects = certificate.required_object_signatures?.length ?
    certificate.required_object_signatures.map(([source, target]) => `${source} -> ${target}`).join(" OR ") :
    "untyped";
  const governedObject = certificate.governed_object ?
    `${certificate.governed_object.source} (${certificate.governed_object.source_type}) -> ${certificate.governed_object.target} (${certificate.governed_object.target_type})` :
    "not bound in this corpus-level certificate";
  const adjudication = certificate.adjudication_required ?
    certificate.adjudication_approved ? "required and approved" : "required; approval absent" :
    "not required for this claim";
  const triggeredReasons = certificate.triggered_reasons?.length ? certificate.triggered_reasons.join(", ") : "none";
  const decisionReason = certificate.decision_reason || "none";
  const projectedObject = certificate.fallback_projected_object ?
    `${certificate.fallback_projected_object.source} (${certificate.fallback_projected_object.source_type}) -> ${certificate.fallback_projected_object.target} (${certificate.fallback_projected_object.target_type})` :
    "none";
  const fallbackProjection = certificate.fallback_projection || "none";
  const projectionProvenance = certificate.fallback_projection_provenance?.length ?
    certificate.fallback_projection_provenance.join(" ") : "none";
  const refusalClass = certificate.refusal_class || "not applicable";
  const policyAdmissibility = certificate.policy_admissible ? "admissible" : "not admissible";
  const representationAuthorization = certificate.requested_representation_authorized ? "authorized" : "blocked";
  elements["certificate-panel"].className = `certificate-panel ${certificate.decision.toLowerCase()}`;
  elements["certificate-panel"].innerHTML = `
    <div><span class="certificate-label">Decision</span><div class="decision-badge">${escapeHtml(certificate.decision)}</div><p>Policy ${escapeHtml(certificate.policy_version)}</p><p><strong>Family:</strong> ${escapeHtml(certificate.claim_family?.replaceAll("-", " ") || "legacy policy")}</p><p><strong>Policy admissibility:</strong> ${escapeHtml(policyAdmissibility)}</p></div>
    <div><span class="certificate-label">Requested claim</span><h2>${escapeHtml(certificate.claim_type.replaceAll("-", " "))}</h2><p><strong>Refusal class:</strong> ${escapeHtml(refusalClass)}</p><p><strong>Controlling reason:</strong> ${escapeHtml(decisionReason)}</p><p><strong>All triggered reasons:</strong> ${escapeHtml(triggeredReasons)}</p><p><strong>Representation:</strong> ${escapeHtml(representationAuthorization)}</p><p><strong>Fallback:</strong> ${escapeHtml(fallback)}</p><p><strong>Encoding:</strong> ${escapeHtml(certificate.allowed_encoding.replaceAll("-", " "))}</p><p><strong>Export:</strong> ${escapeHtml(exportStatus)}</p></div>
    <div><span class="certificate-label">Typed evidence contract</span><p><strong>Required objects:</strong> ${escapeHtml(requiredObjects)}</p><p><strong>Governed object:</strong> ${escapeHtml(governedObject)}</p><p><strong>Object match:</strong> ${certificate.object_type_match ? "pass" : "fail"}</p><p><strong>Adjudication:</strong> ${escapeHtml(adjudication)}</p><p class="channel-list"><strong>Observed:</strong> ${escapeHtml(certificate.observed_channels.join(", ") || "none")}</p><p class="channel-list"><strong>Required:</strong> ${escapeHtml(required)}</p><p><strong>Counterevidence:</strong> ${escapeHtml(counterevidence)}</p><p>${escapeHtml(certificate.allowed_statement)}</p></div>
    <div><span class="certificate-label">Gates, witness, remediation</span><p><strong>Provenance:</strong> ${certificate.provenance_complete ? "complete" : "incomplete"}</p><p><strong>Specification persistence:</strong> ${escapeHtml(survival)}</p><p><strong>Uncertainty / dependence:</strong> ${certificate.uncertainty_adequate ? "adequate" : "not established"} / ${certificate.dependence_adequate ? "adequate" : "not established"}</p><p><strong>Fallback projection:</strong> ${escapeHtml(fallbackProjection)}</p><p><strong>Projected object:</strong> ${escapeHtml(projectedObject)}</p><p><strong>Projection provenance:</strong> ${escapeHtml(projectionProvenance)}</p><ul>${certificate.witness.map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>All applicable gates passed.</li>"}</ul><p>${escapeHtml(certificate.remediation.join(" ") || "No remediation required.")}</p></div>`;
  elements["export-button"].disabled = !certificate.allowed_export;
  elements["export-button"].textContent = certificate.allowed_export ? "Export governed graph" : certificate.fallback_claim ? "Requested export blocked" : "Export blocked";
  elements["export-button"].title = exportStatus;
}

function percentage(value) {
  return `${(Number(value) * 100).toFixed(value === 0 || value === 1 ? 0 : 3)}%`;
}

function renderWalkthrough(step) {
  if (!externalValidation) return;
  const { mrpc, paws, snli, al_cpl: alCpl, torque } = externalValidation.datasets;
  const panels = {
    lexical: {
      decision: "REFUSE",
      tone: "refuse",
      request: "Sentential paraphrase equivalence from lexical overlap",
      observed: "co-occurrence",
      required: "annotation-semantic-equivalence",
      representation: "No semantic relation; lexical association is the policy-preferred fallback",
      evidence: `PAWS contains ${paws.lexical_overlap.high_overlap_non_paraphrase_count.toLocaleString()} high-overlap non-paraphrases (${percentage(paws.lexical_overlap.high_overlap_non_paraphrase_rate)} of negative labels).`
    },
    semantic: {
      decision: "ADMIT / REFUSE",
      tone: "qualify",
      request: "Sentential paraphrase equivalence or non-paraphrase",
      observed: "annotation-semantic-equivalence, with explicit negative counterevidence",
      required: "annotation-semantic-equivalence",
      representation: "Undirected semantic relation for a positive label; no relation for a negative label",
      evidence: `${mrpc.record_count.toLocaleString()} MRPC and ${paws.record_count.toLocaleString()} PAWS judgments produce ${percentage(paws.contract_outcomes.positive_annotation_admission_rate)} matched admission and ${percentage(paws.contract_outcomes.negative_counterevidence_refusal_rate)} matched refusal.`
    },
    entailment: {
      decision: "ADMIT ENTAILMENT / REFUSE OTHERWISE",
      tone: "admit",
      request: "Premise-to-hypothesis semantic entailment",
      observed: "annotation-entailment",
      required: "annotation-entailment in the requested direction",
      representation: "Directed arrow only for annotated premise-to-hypothesis entailment",
      evidence: `${snli.record_count.toLocaleString()} labeled SNLI pairs produce ${percentage(snli.contract_outcomes.directional_annotation_admission_rate)} entailment admission, ${percentage(snli.contract_outcomes.neutral_insufficient_support_refusal_rate)} neutral insufficiency refusal, ${percentage(snli.contract_outcomes.contradiction_counterevidence_refusal_rate)} contradiction refusal, and ${percentage(snli.contract_outcomes.annotation_nontransfer_refusal_rate)} reversal annotation non-transfer.`
    },
    prerequisite: {
      decision: "ADMIT FORWARD / REFUSE REVERSE",
      tone: "admit",
      request: "Concept prerequisite in a requested direction",
      observed: "annotation-prerequisite scoped to an ordered concept pair",
      required: "pair-matched prerequisite annotation or prerequisite-bearing reference",
      representation: "Directed prerequisite arrow only for the supported concept order",
      evidence: `${alCpl.record_count.toLocaleString()} AL-CPL candidate pairs include ${alCpl.label_counts.prerequisite.toLocaleString()} positives. Matched admission, negative refusal, and reverse non-transfer are ${percentage(alCpl.contract_outcomes.matched_annotation_admission_rate)}, ${percentage(alCpl.contract_outcomes.negative_counterevidence_refusal_rate)}, and ${percentage(alCpl.contract_outcomes.reverse_nontransfer_refusal_rate)}.`
    },
    temporal: {
      decision: "ADMIT EVENT ORDER / REFUSE MENTION ORDER",
      tone: "admit",
      request: "Event temporal precedence in a requested direction",
      observed: "adjudicated TORQUE before/after annotation scoped to an event pair",
      required: "pair-matched event-order annotation",
      representation: "Directed temporal arrow only for the supported event order",
      evidence: `${torque.record_count.toLocaleString()} usable TORQUE dev relations produce ${percentage(torque.contract_outcomes.matched_annotation_admission_rate)} matched admission, ${percentage(torque.contract_outcomes.mention_order_refusal_rate)} mention-order refusal, and ${percentage(torque.contract_outcomes.reverse_nontransfer_refusal_rate)} reverse refusal. Public test answers remain excluded.`
    },
    boundary: {
      decision: "REFUSE MISMATCH",
      tone: "refuse",
      request: "Temporal, prerequisite, causal, theme, or analyst-benefit claim",
      observed: "semantic-equivalence or entailment annotation",
      required: "a construct-matched channel for the requested claim",
      representation: "No stronger relation is exported",
      evidence: `Cross-construct admission is ${percentage(Math.max(...Object.values(externalValidation.datasets).map((dataset) => dataset.contract_outcomes.cross_construct_admission_rate)))} across all five external datasets.`
    }
  };
  const panel = panels[step];
  elements["walkthrough-content"].className = `walkthrough-content ${panel.tone}`;
  elements["walkthrough-content"].innerHTML = `
    <div><span>Decision</span><strong>${escapeHtml(panel.decision)}</strong></div>
    <div><span>Requested claim</span><strong>${escapeHtml(panel.request)}</strong><p>${escapeHtml(panel.evidence)}</p></div>
    <div><span>Observed channel</span><strong>${escapeHtml(panel.observed)}</strong><p><b>Required:</b> ${escapeHtml(panel.required)}</p></div>
    <div><span>Permitted representation</span><strong>${escapeHtml(panel.representation)}</strong></div>`;
  document.querySelectorAll("[data-walkthrough]").forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.walkthrough === step));
  });
}

async function loadValidationEvidence() {
  try {
    const response = await fetch("../results/external_validation.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    externalValidation = await response.json();
    const total = Object.values(externalValidation.datasets).reduce((sum, dataset) => sum + dataset.record_count, 0);
    elements["validation-count"].textContent = `${total.toLocaleString()} relation records | policy ${externalValidation.policy_version}`;
    renderWalkthrough("lexical");
  } catch (error) {
    elements["validation-count"].textContent = "External evidence unavailable";
    elements["walkthrough-content"].innerHTML = `<p>Could not load aggregate policy stress-test evidence: ${escapeHtml(error.message)}</p>`;
  }
}

function matchingComponent(component, query) {
  if (!query) return true;
  return component.some((term) => term.toLowerCase().includes(query));
}

function renderComponents() {
  const query = elements.search.value.trim().toLowerCase();
  const shown = current.components
    .map((component, index) => ({ component, index }))
    .filter(({ component }) => matchingComponent(component, query))
    .slice(0, 100);
  elements["component-list"].innerHTML = shown.map(({ component, index }) => `
    <li><button class="component-button" type="button" data-component="${index}">
      <span class="component-id">C${index + 1}</span>
      <span class="component-terms">${escapeHtml(component.join(", "))}</span>
      <span class="component-size" aria-label="${component.length} members">${component.length}</span>
    </button></li>`).join("");
  elements["component-count"].textContent = `${shown.length} shown`;
  document.getElementById("components-heading").textContent = current.noRelation ? "Unrelated terms" : current.conditionalAsymmetry ? "Conditional SCC candidates" : current.directed ? "Semantic SCC cores" : "Association groups";
  elements["component-list"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => showComponent(Number(button.dataset.component)));
  });
}

// certificate-guarded-output-entry-point: inspector graph-mark rendering; guard=requireCertificate
function renderGraph() {
  requireCertificate(current.certificate);
  const visible = current.components.slice(0, 32);
  const visibleSet = new Set(visible.map((_, index) => index));
  const columns = 6;
  const positions = visible.map((component, index) => ({
    x: 82 + (index % columns) * 145,
    y: 70 + Math.floor(index / columns) * 88,
    radius: Math.min(32, 17 + Math.sqrt(component.length) * 4)
  }));
  const lines = [...current.condensation].map((value) => value.split(":").map(Number))
    .filter(([source, target]) => visibleSet.has(source) && visibleSet.has(target))
    .map(([source, target]) => {
      const sourcePosition = positions[source];
      const targetPosition = positions[target];
      const midpointX = (sourcePosition.x + targetPosition.x) / 2;
      const midpointY = (sourcePosition.y + targetPosition.y) / 2;
      const angle = Math.atan2(targetPosition.y - sourcePosition.y, targetPosition.x - sourcePosition.x) * 180 / Math.PI;
      const relationClass = current.conditionalAsymmetry ? "conditional-asymmetry" : current.contested ? "contested-relation" : "semantic-direction";
      const glyph = current.conditionalAsymmetry ? `<g class="conditional-glyph" transform="translate(${midpointX} ${midpointY}) rotate(${angle})" aria-hidden="true"><rect class="glyph-backdrop" x="-15" y="-9" width="30" height="18" rx="2"></rect><path class="glyph-origin" d="M -9 -6 V 6"></path><circle class="glyph-target" cx="9" cy="0" r="5"></circle><path class="glyph-stem" d="M -7 0 H 4"></path></g>` : "";
      const conflictGlyph = current.contested ? `<g class="conflict-glyph" transform="translate(${midpointX} ${midpointY})" aria-hidden="true"><circle cx="0" cy="0" r="9"></circle><path d="M -4 -4 L 4 4 M 4 -4 L -4 4"></path></g>` : "";
      return `<line class="graph-edge ${relationClass}" x1="${sourcePosition.x}" y1="${sourcePosition.y}" x2="${targetPosition.x}" y2="${targetPosition.y}"></line>${glyph}${conflictGlyph}`;
    })
    .join("");
  const nodes = visible.map((component, index) => {
    const position = positions[index];
    const type = component.length > 1 ? "core" : "single";
    const label = `C${index + 1}, ${component.length} member${component.length === 1 ? "" : "s"}: ${component.slice(0, 5).join(", ")}`;
    return `<g class="graph-node ${type}" data-component="${index}" tabindex="0" role="button" aria-label="${escapeHtml(label)}">
      <circle cx="${position.x}" cy="${position.y}" r="${position.radius}"></circle>
      <text x="${position.x}" y="${position.y - 1}">C${index + 1}</text>
      <text class="size-text" x="${position.x}" y="${position.y + 14}">n=${component.length}</text>
    </g>`;
  }).join("");
  const marker = current.semanticDirected ? `<defs><marker id="arrowhead" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#356d8a"></polygon></marker></defs>` : "";
  const graphTitle = current.noRelation ? "No authorized relation" : current.contested ? "Contested relation graph" : current.conditionalAsymmetry ? "Qualified conditional-asymmetry graph" : current.semanticDirected ? "Admitted semantic-direction graph" : "Undirected association groups";
  const graphDescription = current.noRelation ?
    "Terms are shown without connecting marks because the certificate authorizes no relation." : current.conditionalAsymmetry ?
    "Components are labeled C1 onward. Dashed bar-to-ring glyphs encode prevalence-derived conditional orientation without semantic arrowheads." : current.semanticDirected ?
      "Components are labeled C1 onward. Solid arrowheads encode construct-matched admitted semantic direction." :
      current.contested ? "Components are labeled C1 onward. Interrupted lines and conflict marks encode construct-matched disagreement; ordinary semantic export is blocked." :
        "Groups are labeled C1 onward and use undirected lexical associations supplied by the selected claim contract.";
  elements["graph-view"].innerHTML = `<title id="graph-title">${graphTitle}</title><desc id="graph-description">${graphDescription}</desc>${marker}${lines}${nodes}`;
  document.getElementById("graph-heading").textContent = current.noRelation ? "No authorized relation" : current.contested ? "Contested relation" : current.conditionalAsymmetry ? "Qualified conditional orientation" : current.semanticDirected ? "Admitted semantic direction" : "Undirected association overview";
  document.getElementById("legend-core-label").textContent = current.noRelation ? "Term" : current.directed ? "Nontrivial SCC" : "Nontrivial group";
  const legendMark = document.getElementById("legend-relation-mark");
  legendMark.className = `legend-relation ${current.noRelation ? "none" : current.contested ? "contested" : current.conditionalAsymmetry ? "conditional" : current.semanticDirected ? "semantic" : "lexical"}`;
  document.getElementById("legend-relation-label").textContent = current.noRelation ? "No connecting mark" : current.contested ? "Contested relation" : current.conditionalAsymmetry ? "Statistical bar-to-ring glyph" : current.semanticDirected ? "Semantic arrow" : "Lexical link";
  document.getElementById("graph-note").textContent = current.noRelation ?
    "The requested claim is refused, and no independently supported fallback relation is available." : current.conditionalAsymmetry ?
    "Dashed bar-to-ring marks encode prevalence-derived conditional orientation, not temporal, prerequisite, entailment, or causal direction." : current.semanticDirected ?
      "Solid arrowheads are reserved for construct-matched semantic direction admitted by the certificate." :
      current.contested ? "Interrupted lines and conflict marks preserve disagreement without authorizing an ordinary semantic arrow or export." :
        "The requested stronger semantics are unavailable; the view uses undirected lexical association groups.";
  elements["graph-view"].querySelectorAll(".graph-node").forEach((node) => {
    const activate = () => showComponent(Number(node.dataset.component));
    node.addEventListener("click", activate);
    node.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") activate(); });
  });
}

function showComponent(index) {
  const component = current.components[index];
  const memberSet = new Set(component);
  const relevant = current.edges.filter((edge) => memberSet.has(edge.source) || memberSet.has(edge.target));
  document.querySelectorAll(".component-button").forEach((button) => button.classList.toggle("active", Number(button.dataset.component) === index));
  elements["detail-content"].innerHTML = `
    <h3>Component C${index + 1}</h3>
    <p>${component.length > 1 ? (current.conditionalAsymmetry ? "Nontrivial conditional-orientation SCC candidate" : current.directed ? "Nontrivial semantic-direction SCC candidate" : "Nontrivial undirected association group") : "Singleton component"}</p>
    <div class="term-cloud">${component.map((term) => `<span>${escapeHtml(term)}</span>`).join("")}</div>
    <p><strong>${relevant.length}</strong> incident visible relations. Component membership is structural and is not a semantic theme label.</p>
    ${relevant.slice(0, 8).map((edge) => `<button class="edge-link" type="button" data-edge="${analysis.edges.indexOf(edge)}">${escapeHtml(edge.source)} to ${escapeHtml(edge.target)}</button>`).join("<br>")}`;
  elements["detail-content"].querySelectorAll("[data-edge]").forEach((button) => button.addEventListener("click", () => showEdge(analysis.edges[Number(button.dataset.edge)])));
}

function showEdge(edge) {
  const connector = current.directed ? " to " : " / ";
  elements["detail-content"].innerHTML = `
    <h3>${escapeHtml(edge.source)}${connector}${escapeHtml(edge.target)}</h3>
    <p>${escapeHtml(current.certificate.allowed_statement)}</p>
    <div class="relation-facts">
      <div><span>Confidence</span><strong>${edge.confidence.toFixed(3)}</strong></div>
      <div><span>Lift</span><strong>${edge.lift.toFixed(3)}</strong></div>
      <div><span>Support</span><strong>${edge.support}</strong></div>
      <div><span>Excerpts</span><strong>${edge.evidence.length}</strong></div>
    </div>
    ${edge.evidence.length ? edge.evidence.map((item) => `<blockquote class="evidence-item"><cite>${escapeHtml(item.document_id)} | ${escapeHtml(item.unit_id)}</cite>${escapeHtml(item.excerpt)}</blockquote>`).join("") : "<p>No excerpt retained for this relation.</p>"}`;
}

function renderComparison() {
  const directedComponents = stronglyConnectedComponents(analysis.nodes, current.requestedEdges);
  const weakGroups = weakComponents(analysis.nodes, current.requestedEdges);
  const largestWeak = Math.max(0, ...weakGroups.map((component) => component.length));
  const largestScc = directedComponents[0]?.length || 0;
  elements["comparison-content"].innerHTML = `
    <div><span>Directed SCC</span><strong>${directedComponents.length} groups</strong><p>Largest group: ${largestScc}. Requires mutual directed reachability.</p></div>
    <div><span>Symmetrized or weak</span><strong>${weakGroups.length} groups</strong><p>Largest group: ${largestWeak}. Direction is discarded.</p></div>
    <div><span>No-SCC singleton</span><strong>${analysis.nodes.length} groups</strong><p>Largest group: ${analysis.nodes.length ? 1 : 0}. All relations are removed.</p></div>`;
}

function renderEdges() {
  const query = elements.search.value.trim().toLowerCase();
  const shown = current.edges.filter((edge) => !query || [edge.source, edge.target, ...edge.evidence.map((item) => item.excerpt)].some((value) => value.toLowerCase().includes(query))).slice(0, 200);
  elements["edge-count"].textContent = `${shown.length} of ${current.edges.length} shown`;
  document.getElementById("edges-heading").textContent = current.noRelation ? "Authorized relations" : current.conditionalAsymmetry ? "Conditional orientations" : current.semanticDirected ? "Semantic directions" : "Lexical associations";
  document.getElementById("edge-source-heading").textContent = current.conditionalAsymmetry ? "Condition term" : current.directed ? "Source" : "Term A";
  document.getElementById("edge-target-heading").textContent = current.conditionalAsymmetry ? "Co-occurring term" : current.directed ? "Target" : "Term B";
  elements["edge-table"].innerHTML = shown.map((edge) => `<tr>
    <td><button class="edge-link" type="button" data-index="${analysis.edges.indexOf(edge)}">${escapeHtml(edge.source)}</button></td>
    <td>${escapeHtml(edge.target)}</td><td>${edge.confidence.toFixed(3)}</td><td>${edge.lift.toFixed(3)}</td><td>${edge.support}</td><td>${edge.evidence.length}</td>
  </tr>`).join("");
  elements["edge-table"].querySelectorAll("button").forEach((button) => button.addEventListener("click", () => showEdge(analysis.edges[Number(button.dataset.index)])));
}

function render() {
  deriveState();
  renderCertificate();
  renderMetrics();
  renderComponents();
  renderGraph();
  renderComparison();
  renderEdges();
  const structure = current.noRelation ? "unrelated singleton terms" : current.conditionalAsymmetry ? "conditional SCC candidates" : current.directed ? "semantic SCCs" : "association groups";
  elements.status.textContent = `${analysis.corpus_name}: ${current.certificate.decision}; recomputed ${current.components.length} ${structure} from ${current.edges.length} admissible relations.`;
}

async function loadDataset(key) {
  elements.status.classList.remove("error");
  elements.status.textContent = `Loading ${datasets[key].label}...`;
  try {
    const response = await fetch(datasets[key].path);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    analysis = await response.json();
    if (!Array.isArray(analysis.claim_certificates) || !analysis.claim_certificates.length) throw new Error("analysis lacks executable claim certificates");
    analysis.claim_certificates.forEach(requireCertificate);
    if (new Set(analysis.claim_certificates.map((certificate) => certificate.claim_type)).size !== analysis.claim_certificates.length) throw new Error("analysis contains duplicate claim certificates");
    const relationTypes = [...new Set(analysis.edges.map((edge) => edge.relation_type))].sort();
    elements["relation-select"].innerHTML = `<option value="all">All relation types</option>${relationTypes.map((type) => `<option value="${escapeHtml(type)}">${escapeHtml(type)}</option>`).join("")}`;
    elements["claim-select"].innerHTML = analysis.claim_certificates.map((certificate) => `<option value="${escapeHtml(certificate.claim_type)}">${escapeHtml(certificate.claim_type.replaceAll("-", " "))}</option>`).join("");
    const requestedClaim = new URLSearchParams(globalThis.location.search).get("claim");
    elements["claim-select"].value = analysis.claim_certificates.some((certificate) => certificate.claim_type === requestedClaim) ? requestedClaim : "lexical-association";
    const configured = analysis.configuration?.relation_extractor || {};
    elements.confidence.value = configured.min_confidence ?? 0.65;
    elements.lift.value = configured.min_lift ?? 1.05;
    elements["confidence-output"].value = Number(elements.confidence.value).toFixed(2);
    elements["lift-output"].value = Number(elements.lift.value).toFixed(2);
    elements["configuration-note"].textContent = `Schema ${analysis.schema_version}; ${analysis.configuration?.edge_semantics || "edge semantics unavailable"}`;
    elements["detail-content"].innerHTML = "<p>Select a component or relation to inspect its traceable source excerpts.</p>";
    render();
  } catch (error) {
    elements.status.classList.add("error");
    elements.status.textContent = `Could not load ${datasets[key].path}: ${error.message}. Serve the repository over HTTP.`;
  }
}

function downloadJson(filename, value) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

elements["corpus-select"].innerHTML = Object.entries(datasets).map(([key, dataset]) => `<option value="${key}">${dataset.label}</option>`).join("");
elements["corpus-select"].addEventListener("change", (event) => loadDataset(event.target.value));
elements.confidence.addEventListener("input", () => { elements["confidence-output"].value = Number(elements.confidence.value).toFixed(2); render(); });
elements.lift.addEventListener("input", () => { elements["lift-output"].value = Number(elements.lift.value).toFixed(2); render(); });
elements["relation-select"].addEventListener("change", render);
elements["claim-select"].addEventListener("change", render);
elements.search.addEventListener("input", () => { renderComponents(); renderEdges(); });
// certificate-guarded-output-entry-point: inspector requested-claim export; guard=requireCertificate
elements["export-button"].addEventListener("click", () => {
  requireCertificate(current.certificate);
  if (!current.certificate.allowed_export) throw new Error("the active certificate blocks requested-claim export");
  downloadJson("themegraph-filtered.json", {
  corpus_name: analysis.corpus_name,
  requested_claim: current.certificate.claim_type,
  decision: current.certificate.decision,
  exported_claim: current.certificate.decision === "REFUSE" ? current.certificate.fallback_claim : current.certificate.claim_type,
  visual_encoding: current.certificate.allowed_encoding,
  allowed_statement: current.certificate.allowed_statement,
  certificate: current.certificate,
  filters: { min_confidence: current.confidence, min_lift: current.lift, relation_type: current.relation },
  nodes: analysis.nodes,
  edges: current.directed ? current.edges : current.edges.map((edge) => ({
    term_a: [edge.source, edge.target].sort()[0],
    term_b: [edge.source, edge.target].sort()[1],
    relation_type: "lexical-association",
    support: edge.support,
    lift: edge.lift,
    evidence: edge.evidence
  })),
  components: current.components,
  warning: "The export contains only the representation admitted by the attached certificate."
  });
});
elements["manifest-button"].addEventListener("click", () => downloadJson("themegraph-manifest.json", {
  generated_at: new Date().toISOString(),
  corpus_name: analysis.corpus_name,
  schema_version: analysis.schema_version,
  source_file: datasets[elements["corpus-select"].value].path,
  selected_certificate: current.certificate,
  configuration: analysis.configuration,
  filters: { min_confidence: current.confidence, min_lift: current.lift, relation_type: current.relation }
}));

document.querySelectorAll("[data-walkthrough]").forEach((button) => {
  button.addEventListener("click", () => renderWalkthrough(button.dataset.walkthrough));
});

loadValidationEvidence();
loadDataset("synthetic");