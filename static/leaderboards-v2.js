(function(){
  function renderLeaderboardPage(data,mode){
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

    app.innerHTML=`<section class="screen"><div class="page-head"><p class="eyebrow">${reverse?'REVERSE LEADERBOARD':'BEST INSPECTION RECORDS'}</p><h1>${heading}</h1><p>${intro}</p><div class="chips leader-mode"><button class="chip ${!reverse?'selected':''}" data-leader-mode="best">Best scores</button><button class="chip ${reverse?'selected':''}" data-leader-mode="risk">Highest risk</button></div></div><div class="leader-method"><strong>Fair-comparison rules</strong><span>${Number(m.months||18)}-month window · chains need ${Number(m.minimum_chain_locations||3)} locations · neighborhoods need ${Number(m.minimum_neighborhood_restaurants||25)} restaurants</span><small>${Number(m.eligible_facilities||0).toLocaleString()} facilities currently qualify. Records with cited but unmapped violations are excluded rather than scored as zero.${m.snapshot_recalibrated_during_deploy?' Rankings are using a temporary recalibration while the current snapshot finishes rebuilding.':''}</small></div><div class="leader-columns"><section class="leader-section"><div class="leader-title"><div><p class="eyebrow">CHAINS</p><h2>${chainTitle}</h2></div><span>3+ SF locations</span></div>${leaderboardRows(chains,'location_count','location')}</section><section class="leader-section"><div class="leader-title"><div><p class="eyebrow">NEIGHBORHOODS</p><h2>${neighborhoodTitle}</h2></div><span>25+ restaurants</span></div>${leaderboardRows(neighborhoods,'restaurant_count','restaurant')}</section></div><div class="source-note">${sourceNote}</div></section>`;
    document.querySelectorAll('[data-leader-mode]').forEach(button=>{
      button.onclick=()=>renderLeaderboardPage(data,button.dataset.leaderMode);
    });
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
