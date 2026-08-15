(function(){
  // Match the numeric leaderboard colors to risk model 2026.08.15.4.
  leaderboardTone=function(score){
    const n=Number(score||0);
    return n<20?'low':n<45?'moderate':n<70?'elevated':n<90?'high':'critical';
  };

  const chainMembersCache=new Map();

  async function chainMembers(name){
    const key=String(name||'').toUpperCase();
    if(!chainMembersCache.has(key)){
      chainMembersCache.set(key,api('/api/restaurants?'+new URLSearchParams({q:name,limit:'200'}).toString()));
    }
    return chainMembersCache.get(key);
  }

  function interactiveRows(items,countKey,countLabel,kind){
    if(!items?.length)return'<div class="empty">Not enough eligible inspection records to publish this ranking yet.</div>';
    return `<div class="leader-list">${items.map((item,index)=>`<article class="leader-row" role="button" tabindex="0" data-leader-kind="${kind}" data-leader-index="${index}" aria-label="View restaurants for ${esc(item.name)}"><div class="leader-rank">${index+1}</div><div class="leader-main"><strong>${esc(item.name)}</strong><span class="leader-count">${Number(item[countKey]||0)} ${countLabel}${Number(item[countKey]||0)===1?'':'s'} · ${Number(item.pass_rate||0).toFixed(1)}% Pass</span><small>Median risk ${Number(item.median_risk||0).toFixed(1)} · latest ${fmt(item.latest_inspection_date)}</small></div><div class="leader-score"><strong class="risk-text ${leaderboardTone(item.average_risk)}">${Number(item.average_risk||0).toFixed(1)}</strong><span>avg risk</span></div></article>`).join('')}</div>`;
  }

  function renderGroup(kind,item,items,mode){
    const chain=kind==='chain';
    const noun=chain?'locations':'restaurants';
    state.route='leaders';
    setNav('leaders');
    app.innerHTML=`<section class="screen"><button class="back" id="leaderBack">← Back to leaderboard</button><div class="page-head"><p class="eyebrow">${chain?'CHAIN':'NEIGHBORHOOD'} DETAILS</p><h1>${esc(item.name)}</h1><p>${items.length} known ${noun} in the loaded SF inspection history. Leaderboard average: <strong>${Number(item.average_risk||0).toFixed(1)}</strong>.</p>${chain&&items.length>Number(item.location_count||0)?`<p class="muted-text">${Number(item.location_count||0)} location${Number(item.location_count||0)===1?'':'s'} had a recent comparable inspection in the leaderboard window; older locations remain searchable but do not change the recent-risk average.</p>`:''}</div><div class="list">${items.map(card).join('')||'<div class="empty">No restaurant records found.</div>'}</div></section>`;
    bindList();
    document.querySelector('#leaderBack').onclick=()=>renderLeaderboardPage(window.__leaderboardData||{},mode||'best');
  }

  async function openGroup(kind,item,mode){
    loading();
    try{
      const items=kind==='chain'
        ?await chainMembers(item.name)
        :await api('/api/restaurants?'+new URLSearchParams({neighborhood:item.name,limit:'200'}).toString());
      renderGroup(kind,item,items,mode);
    }catch(e){
      errorView(e);
    }
  }

  function bindLeaderboardInteractions(chains,neighborhoods,mode){
    document.querySelectorAll('[data-leader-kind]').forEach(row=>{
      const kind=row.dataset.leaderKind;
      const index=Number(row.dataset.leaderIndex||0);
      const item=(kind==='chain'?chains:neighborhoods)[index];
      if(!item)return;
      const activate=()=>openGroup(kind,item,mode);
      row.onclick=activate;
      row.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}};
    });

    // The ranking average intentionally uses only recent comparable inspections, but
    // the footprint label should reflect every loaded inspection location. Resolve
    // chain membership through the same search index users see, and show both counts.
    chains.forEach(async(item,index)=>{
      try{
        const members=await chainMembers(item.name);
        const row=document.querySelector(`[data-leader-kind="chain"][data-leader-index="${index}"] .leader-count`);
        if(!row)return;
        const recent=Number(item.location_count||0);
        const known=members.length;
        row.textContent=known>recent
          ?`${known} known locations · ${recent} recent score${recent===1?'':'s'} · ${Number(item.pass_rate||0).toFixed(1)}% Pass`
          :`${known} location${known===1?'':'s'} · ${Number(item.pass_rate||0).toFixed(1)}% Pass`;
      }catch(_){/* keep server-provided count if the supplemental lookup fails */}
    });
  }

  function renderLeaderboardPage(data,mode){
    window.__leaderboardData=data;
    const reverse=mode==='risk';
    const m=data.methodology||{};
    const chains=reverse?(data.highest_risk_chains||[]):(data.chains||[]);
    const neighborhoods=reverse?(data.highest_risk_neighborhoods||[]):(data.neighborhoods||[]);
    const heading=reverse?'Highest-risk inspection records':'Best inspection records';
    const intro=reverse
      ?'These rankings surface chains and neighborhoods with the highest average Foodborne Illness Risk Index among eligible recent inspections. <strong>Higher is worse.</strong>'
      :'Restaurants are ranked by the average Foodborne Illness Risk Index from each location’s most recent rated inspection. <strong>Lower is better.</strong>';
    const chainTitle=reverse?'Highest-risk chain records':'Best chain records';
    const neighborhoodTitle=reverse?'Highest-risk neighborhood records':'Best neighborhood records';
    const sourceNote=reverse
      ?`The reverse leaderboard uses the exact same sample thresholds as the best-score list. It is an independent comparison built from SFDPH/DataSF inspection records and risk model ${esc(m.model_version||'current')}; it is not an official San Francisco ranking or a prediction that someone will become ill.`
      :`These are independent comparative rankings built from SFDPH/DataSF inspection records and the SF Food Check risk model ${esc(m.model_version||'current')}. They are not official San Francisco rankings or grades.`;

    app.innerHTML=`<section class="screen"><div class="page-head"><p class="eyebrow">${reverse?'REVERSE LEADERBOARD':'BEST INSPECTION RECORDS'}</p><h1>${heading}</h1><p>${intro}</p><div class="chips leader-mode"><button class="chip ${!reverse?'selected':''}" data-leader-mode="best">Best scores</button><button class="chip ${reverse?'selected':''}" data-leader-mode="risk">Highest risk</button></div></div><div class="leader-method"><strong>Fair-comparison rules</strong><span>${Number(m.months||18)}-month scoring window · chains need ${Number(m.minimum_chain_locations||3)} recent comparable locations · neighborhoods need ${Number(m.minimum_neighborhood_restaurants||25)} restaurants</span><small>${Number(m.eligible_facilities||0).toLocaleString()} facilities currently qualify for scoring. Historical records remain searchable and can appear in chain drilldowns without changing a recent leaderboard average.${m.snapshot_recalibrated_during_deploy?' Rankings are using a temporary recalibration while the current snapshot finishes rebuilding.':''}</small></div><div class="leader-columns"><section class="leader-section"><div class="leader-title"><div><p class="eyebrow">CHAINS</p><h2>${chainTitle}</h2></div><span>Click to view locations</span></div>${interactiveRows(chains,'location_count','location','chain')}</section><section class="leader-section"><div class="leader-title"><div><p class="eyebrow">NEIGHBORHOODS</p><h2>${neighborhoodTitle}</h2></div><span>Click to view restaurants</span></div>${interactiveRows(neighborhoods,'restaurant_count','restaurant','neighborhood')}</section></div><div class="source-note">${sourceNote}</div></section>`;
    document.querySelectorAll('[data-leader-mode]').forEach(button=>{
      button.onclick=()=>renderLeaderboardPage(data,button.dataset.leaderMode);
    });
    bindLeaderboardInteractions(chains,neighborhoods,mode);
  }

  leaders=async function(){
    state.route='leaders';
    setNav('leaders');
    loading();
    try{
      const data=await api('/api/leaderboards?limit=10&months=18');
      renderLeaderboardPage(data,'best');
    }catch(e){
      errorView(e);
    }
  };
})();
