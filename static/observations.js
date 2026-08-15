(function(){
  function observationCard(o){
    const score=Number(o.severity_score??0);
    const level=o.severity_level||'Unrated';
    const source=o.source_label||'Official inspection report';
    return `<div class="observation-item"><div class="observation-head"><strong>Inspector observation</strong><span class="observation-severity ${riskCls(level)}">${score}/100 · ${esc(level)}</span></div><blockquote class="observation-copy">${esc(o.observation_text||'')}</blockquote>${o.severity_rationale?`<p class="observation-why"><strong>Severity rationale:</strong> ${esc(o.severity_rationale)}</p>`:''}${o.corrective_action?`<details class="observation-corrective"><summary>Corrective action from report</summary><p>${esc(o.corrective_action)}</p></details>`:''}<div class="observation-meta"><span>${esc(source)}</span><span>${esc(o.severity_confidence||'unknown')} confidence</span><span>Independent severity assessment</span></div></div>`;
  }

  violationCard=function(v){
    const score=Number(v.risk_score??0);
    const level=v.risk_level||'Unrated';
    const official=v.official_description||'';
    const sourceRisk=v.official_risk_category?`<span class="source-risk">Official risk: ${esc(v.official_risk_category)}</span>`:'';
    const obs=v.observations?.length?`<div class="observation-group"><div class="observation-group-title"><p class="label">INSPECTOR OBSERVATION${v.observations.length===1?'':'S'}</p><span class="observation-count">${v.observations.length} verified report observation${v.observations.length===1?'':'s'}</span></div>${[...v.observations].sort((a,b)=>Number(b.severity_score||0)-Number(a.severity_score||0)).map(observationCard).join('')}</div>`:'';
    return `<div class="violation readable"><div class="violation-top"><div><p class="label">${v.code?`CODE ${esc(v.code)} · `:''}${esc(level).toUpperCase()}</p><strong>${esc(v.normalized_category||official||v.code||'Food-safety finding')}</strong></div><span class="severity ${riskCls(level)}">${score}/100</span></div>${sourceRisk}${v.consumer_description?`<p class="consumer-summary">${esc(v.consumer_description)}</p>`:''}${v.risk_rationale?`<p class="why-it-matters"><strong>Why it matters:</strong> ${esc(v.risk_rationale)}</p>`:''}${obs}${official?`<details><summary>Official published finding</summary><p>${esc(official)}</p></details>`:`<p class="limited-detail"><strong>Description unavailable.</strong> DataSF published the violation code for this inspection without descriptive text that we can map reliably.</p>`}</div>`;
  };

  violations=function(i){
    const mapped=i.violations?.length?[...i.violations].sort((a,b)=>Number(b.risk_score||0)-Number(a.risk_score||0)).map(violationCard).join(''):'<p class="muted-text">No violation details are available in this record.</p>';
    const unmatched=i.unmatched_observations?.length?`<div class="unmatched-observations"><h4>Other inspector observations</h4><p>These verified observations were present in the official report but could not be matched confidently to one published violation code, so they are kept separate rather than guessed.</p>${[...i.unmatched_observations].sort((a,b)=>Number(b.severity_score||0)-Number(a.severity_score||0)).map(observationCard).join('')}</div>`:'';
    return mapped+unmatched;
  };

  reportBlock=function(i){
    const r=i.report;
    if(r&&r.inspector_comments){
      return `<div class="comment"><p class="label">INSPECTOR COMMENTS · ${esc(r.source_label||'Official report')}</p><blockquote>${esc(r.inspector_comments)}</blockquote>${r.corrective_action?`<p class="label">CORRECTIVE ACTION</p><p>${esc(r.corrective_action)}</p>`:''}${r.report_url?`<a class="text-link" href="${esc(r.report_url)}" target="_blank" rel="noopener">View official report ↗</a>`:''}</div>`;
    }
    if(r&&r.report_url){
      const count=Number(i.observation_mapping?.total_count||0);
      return `<div class="comment"><p class="label">OFFICIAL INSPECTION REPORT</p><p class="report-observation-note">${count?`${count} verified violation-level observation${count===1?' is':'s are'} shown above with the related finding${count===1?'':'s'}.`:'This official report is linked, but violation-level observations have not yet been imported.'}</p><a class="text-link" href="${esc(r.report_url)}" target="_blank" rel="noopener">View official report ↗</a></div>`;
    }
    return `<div class="comment muted"><p class="label">INSPECTOR COMMENTS</p><p>Official narrative has not yet been linked for this inspection. SF Food Check does not generate or infer inspector comments or observations.</p></div>`;
  };
})();
