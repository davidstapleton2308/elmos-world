(()=>{'use strict';
const token=new URLSearchParams(location.hash.slice(1)).get('token')||'';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let previewTimer=null,artPreloaded=new Map(),libraryLayout='carousel';
let elmoTheme=localStorage.getItem('elmo-theme')||'forest';let elmoMotion=localStorage.getItem('elmo-motion')||'normal';const controllerMapDefault={a:0,b:1,start:9,lb:4,rb:5,guide:10};let controllerMap=Object.assign({},controllerMapDefault,JSON.parse(localStorage.getItem('elmo-controller-map')||'{}'));let latestNative=null;let diagLast=0;

let state={games:[],gfnGames:[],emulators:{},counts:{all:0,review:0}},selected=localStorage.getItem('elmo-deck-selected')||null,sort='all',screen='library',modal=false,toastTimer,controllerTimestamp=0,buttonDown=false,lastDpad=null,metadataCache={};
let initialRecentFocusDone=false;let menuAudio=null;
function menuSound(){if(localStorage.getItem('elmo-sound')!=='on')return;try{const AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;if(!menuAudio)menuAudio=new AC();if(menuAudio.state!=='running')return;const osc=menuAudio.createOscillator(),gain=menuAudio.createGain();osc.type='sine';osc.frequency.value=520;gain.gain.setValueAtTime(.014,menuAudio.currentTime);gain.gain.exponentialRampToValueAtTime(.001,menuAudio.currentTime+.06);osc.connect(gain).connect(menuAudio.destination);osc.start();osc.stop(menuAudio.currentTime+.065)}catch(e){}}
let gameInputSuspended=false,activeGameTitle='',gateUntilRelease=false,gameLaunchAt=0,gameLaunchMode='direct';
let runningGameId=null,runningGameName='',sessionCheckBusy=false;
function updateSessionPresentation(){
 const isRunning=!!runningGameId;
 const homeVisible=isRunning&&!['playing','launching','menu'].includes(sessionState);
 const chip=$('playingChip');
 if(chip){chip.hidden=!homeVisible;chip.querySelector('.playing-title').textContent=runningGameName||'Game running';}
 document.documentElement.dataset.sessionMode=(isRunning&&sessionState==='playing')?'sleep':'awake';
 if(screen==='library')renderFeatured();
}
function setGameInputSuspended(value,title=''){
 gameInputSuspended=value;if(title)activeGameTitle=title;
 gateUntilRelease=true;prevPad={};lastNav='';
 updateSessionPresentation();
}
async function resumeTrackedGame(){
 if(!runningGameId){notify('No game is currently running.',true);return false;}
 let result;
 try{result=await api('/api/handoff',{});}catch(e){
  notify('Cannot reach game session: '+e.message,true);return false;
 }
 // Foreground denial is normal for exclusive/borderless games. Once the
 // *actual tracked game window exists*, minimizing Elmos is the fallback.
 // Never show a stalled launching stage merely because Windows denied focus.
 if(!result?.focused && !result?.windowReady && !result?.resumableWindow){
  if($('gameMenu').hidden)openGameMenu();
  $('menuForceResume').hidden=false;
  notify('The game window was not found. Try Manual switch or Alt+Tab.',true);
  return false;
 }
 try{await api('/api/shield',{enabled:false});launchShield=false;}catch(e){}
 $('gameMenu').hidden=true;$('gameMenu').classList.remove('visible');
 $('menuForceResume').hidden=true;
 sessionState='playing';setGameInputSuspended(true,runningGameName);
 let minimized=false;
 if(window.pywebview?.api?.minimize){
  try{minimized=await window.pywebview.api.minimize()!==false;}catch(e){}
 }
 if(!minimized){
  document.body.classList.add('game-active-browser');
  notify('The game is running. Select its window with Alt+Tab.',true);
 }
 return true;
}
function homeAfterGameExit(){
 if(!runningGameId && sessionState==='library' && !gameInputSuspended && $('launchStage').hidden)return;
 // The process can exit while its game window is still being discovered or a
 // Windows foreground handoff has failed. Invalidate all pending launch work.
 launchSequence++;
 runningGameId=null;runningGameName='';activeGameTitle='';
 sessionState='library';gameLaunchMode='direct';
 $('gameMenu').hidden=true;$('gameMenu').classList.remove('visible');
 hideLaunchStage();api('/api/shield',{enabled:false}).catch(()=>{});setGameInputSuspended(false);open('library');
 if(window.pywebview?.api?.restore)window.pywebview.api.restore().catch(()=>{});
 reload(false).catch(()=>{});
}
async function checkGameSession(){
 if(sessionCheckBusy||(!runningGameId&&!gameInputSuspended))return;
 // Give a newly spawned process time to initialize, but keep watching it even
 // if the handoff failed and the launch screen is still visible.
 if(performance.now()-gameLaunchAt<1600)return;
 sessionCheckBusy=true;
 try{
  const status=await api('/api/game-session');
  if(status.running){
   const was=runningGameId;
   runningGameId=status.gameId||runningGameId;
   runningGameName=status.gameName||runningGameName||activeGameTitle;
   if(was!==runningGameId)updateSessionPresentation();
  }else if(runningGameId||gameInputSuspended){homeAfterGameExit();}
 }catch(e){}finally{sessionCheckBusy=false;}
}
setInterval(checkGameSession,1250);
window.addEventListener('focus',()=>{if(runningGameId)checkGameSession();});

async function api(url,obj){const options={headers:{'X-SteamMatch-Token':token}};if(obj!==undefined){options.method='POST';options.headers['Content-Type']='application/json';options.body=JSON.stringify(obj)}const r=await fetch(url,options);const data=await r.json();if(!r.ok)throw Error(data.error||'Request failed');return data}
async function safe(fn){try{return await fn()}catch(e){notify(e.message,true);return null}}
function notify(text,bad=false){const x=$('toast');x.textContent=text;x.style.background=bad?'#51302d':'#244531';x.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>x.classList.remove('show'),5000)}
function art(g,slot){if(!g||!g.art?.[slot])return '';return '/api/local-art?id='+encodeURIComponent(g.id)+'&slot='+slot+'&v='+encodeURIComponent(g.artVersion||0)+'&token='+encodeURIComponent(token)}
function cover(g){const portrait=art(g,'portrait');const wide=art(g,'wide')||art(g,'hero');const a=portrait||wide;return a?`<img class="cover-image ${libraryLayout==='cinema'&&!wide?'cover-contain':''}" src="${a}" alt="" loading="lazy" decoding="async">`:`<div class="poster-fallback"><span>✧</span><strong>${esc(g.name)}</strong></div>`}
function game(id){return state.games.find(g=>g.id===id)}
async function reload(force=false){const r=await safe(()=>api('/api/state'+(force?'?refresh=1':'')));if(!r)return;state=r;if(!initialRecentFocusDone){if(!r.games.some(g=>g.id===selected&&!g.hidden)){const all=r.games.filter(g=>!g.hidden&&g.lastPlayed);if(all.length){all.sort((a,b)=>b.lastPlayed-a.lastPlayed);selected=all[0].id;}}initialRecentFocusDone=true;}render()}
function formatHours(seconds){const n=Math.max(0,Number(seconds)||0);return n>=3600?(n/3600).toFixed(1)+'h':Math.floor(n/60)+'m'}
async function renderActivity(){
 const data=await safe(()=>api('/api/activity'));if(!data)return;
 const metrics=[['TOTAL PLAYTIME',formatHours(data.totalSeconds)],['GAME LAUNCHES',data.sessionCount],['PLAYED TITLES',data.gamesPlayed],['FAVORITES',data.favorites]];
 $('activityMetrics').innerHTML=metrics.map(([label,value])=>`<div class="activity-metric"><span>${label}</span><strong>${esc(value)}</strong></div>`).join('');
 function rows(items,host){$(host).innerHTML=items.length?items.map((g,i)=>`<button class="activity-game" data-activity-game="${esc(g.id)}"><span class="activity-rank">${String(i+1).padStart(2,'0')}</span><strong>${esc(g.name)}</strong><small>${formatHours(g.seconds)}</small></button>`).join(''):'<p class="subtle">Your adventures will appear here after you finish playing.</p>';$(host).querySelectorAll('[data-activity-game]').forEach(el=>el.onclick=()=>details(el.dataset.activityGame));}
 rows(data.mostPlayed,'mostPlayedList');rows(data.recent,'recentActivityList');
}
async function refreshLaunchTimeline(){const events=await safe(()=>api('/api/session-history'));if(!events)return;$('launchTimeline').innerHTML=events.length?events.slice().reverse().map(e=>`<div class="timeline-row"><time>${new Date(e.at*1000).toLocaleTimeString()}</time><strong>${esc(e.stage.replaceAll('_',' '))}</strong><span>${esc(e.detail)}</span></div>`).join(''):'<p class="subtle">Launch a game to begin a diagnostic timeline.</p>'}
function applyAtmosphere(){if($('soundChoice'))$('soundChoice').value=localStorage.getItem('elmo-sound')||'off';document.documentElement.dataset.atmosphere=localStorage.getItem('elmo-atmosphere')||'cinematic';document.documentElement.dataset.tv=localStorage.getItem('elmo-tv')||'off';if($('atmosphereChoice'))$('atmosphereChoice').value=document.documentElement.dataset.atmosphere;if($('tvModeChoice'))$('tvModeChoice').value=document.documentElement.dataset.tv;}
let ambientSampleRequest=0;
function updateAmbient(url){
 if(document.documentElement.dataset.atmosphere!=='cinematic'||!url)return;
 const request=++ambientSampleRequest;
 // Images originate from Elmos World's own authenticated local image route.
 const pic=new Image();pic.onload=()=>{if(request!==ambientSampleRequest)return;try{
  const c=document.createElement('canvas');c.width=8;c.height=8;const ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(pic,0,0,8,8);const d=ctx.getImageData(0,0,8,8).data;
  let r=0,g=0,b=0,count=0;for(let i=0;i<d.length;i+=4){if(d[i+3]<200)continue;const l=(d[i]+d[i+1]+d[i+2])/3;if(l<35||l>225)continue;r+=d[i];g+=d[i+1];b+=d[i+2];count++}
  if(!count)return;const a=[r,g,b].map(x=>Math.round(x/count));document.documentElement.style.setProperty('--ambient-rgb',a.join(','));
 }catch(e){}};pic.src=url;
}
function render(){ const providers=$('futurePlatforms');if(providers){providers.innerHTML=(state.platforms||[]).map(x=>`<div class="provider-row"><span><b>${esc(x.name)}</b><small>${x.installed?'Installed locally · owned library not connected':'Application not detected'}</small></span>${x.installed?`<button class="add-btn" data-open-platform="${esc(x.name)}">Open</button>`:'<span>Unavailable</span>'}</div>`).join('');providers.querySelectorAll('[data-open-platform]').forEach(b=>b.onclick=async()=>{const r=await safe(()=>api('/api/open-platform',{name:b.dataset.openPlatform}));if(r)notify('Opening '+b.dataset.openPlatform+'…')});}  renderCollections(); $('totalCount').textContent=state.games.filter(g=>!g.hidden).length+' games';const pending=state.games.filter(g=>g.uncertain&&!g.hidden).length;$('reviewCount').textContent=pending?String(pending):'';$('reviewCount').hidden=pending===0;renderLibrary();renderReview();renderEmulators();renderGfn();$('gamesRoot').value=state.root||'';$('layoutChoice').value=libraryLayout;renderHidden();$('artKey').placeholder=state.keyConfigured?'Key saved — leave empty to keep':'Paste SteamGridDB API key';if(selected&&!game(selected)){selected=null;open('library')} }
function visibleGames(){const q=$('search').value.trim().toLowerCase();let list=state.games.filter(g=>!g.hidden&&(!q||g.name.toLowerCase().includes(q)));if(sort==='favorites')list=list.filter(g=>g.favorite);if(sort==='recent')list.sort((a,b)=>(b.lastPlayed||0)-(a.lastPlayed||0));return list}
function renderLibrary(){
 const list=visibleGames();
 $('emptyCards').hidden=list.length>0;
 $('gameCards').innerHTML=list.map(g=>`<button class="game-card ${selected===g.id?'selected':''}" data-g="${esc(g.id)}"><div class="poster">${cover(g)}${g.favorite?'<span class=\"poster-star\">★</span>':''}${g.uncertain?'<div class=\"poster-badge\">SETUP NEEDED</div>':''}</div><div class="card-meta"><strong>${esc(g.name)}</strong><small>${esc(g.platform||'PC')} · ${g.uncertain?'Choose launcher':g.playSeconds?formatPlaytime(g.playSeconds):g.playCount?g.playCount+' launches':'Ready to play'}</small></div></button>`).join('');
 document.querySelectorAll('.game-card').forEach(el=>{el.onclick=()=>details(el.dataset.g);el.onpointerenter=()=>{};el.onfocus=()=>selectGame(el.dataset.g,true)});
 document.getElementById('gameCards').dataset.layout='deck';
 const deckControls=$('carouselActions');
 if(deckControls) deckControls.hidden=list.length<2;
 const recent=$('consoleShelves'); if(recent) recent.hidden=true;
 const collections=$('collectionShelf'); if(collections) collections.hidden=true;
 const browse=$('browsePreview'); if(browse) browse.hidden=true;
 document.querySelectorAll('.sort-btn').forEach(b=>b.classList.toggle('active',b.dataset.sort===sort));
 renderFeatured();
 syncSelectedCard(true);
 requestAnimationFrame(()=>syncSelectedCard(true));
}
function formatPlaytime(seconds){const m=Math.floor((Number(seconds)||0)/60);return m>=60?(Math.floor(m/60)+'h '+(m%60)+'m played'):m>0?(m+'m played'):'Less than 1m played'}
function renderCollections(){
 const root=$('collectionShelves');if(!root)return;
 const collections=state.collections||[];$('collectionShelf').hidden=!collections.length;
 root.innerHTML=collections.map(c=>{const games=c.gameIds.map(game).filter(g=>g&&!g.hidden);
 return `<section class="shelf-block"><div class="shelf-heading">${esc(c.name)} <span>${games.length} GAMES</span></div><div class="shelf-cards">${games.map(g=>`<button class="shelf-tile" data-shelf-game="${esc(g.id)}"><div class="shelf-image">${g.art?.wide||g.art?.hero?`<img src="${art(g,'wide')||art(g,'hero')}" loading="lazy" decoding="async" alt="">`:cover(g)}</div><strong>${esc(g.name)}</strong></button>`).join('')||'<span class="muted">Add games using their Details page</span>'}</div></section>`}).join('');
 root.querySelectorAll('[data-shelf-game]').forEach(el=>{el.onclick=()=>details(el.dataset.shelfGame);el.onfocus=()=>queuePreview(el.dataset.shelfGame);el.onpointerenter=()=>queuePreview(el.dataset.shelfGame)});
}
async function gameHealth(id){const result=await safe(()=>api('/api/health'+(id?'?id='+encodeURIComponent(id):'')));if(!result)return;
 const issues=result.items.filter(x=>x.status!=='ready');
 const body=`<p><b>${result.ready} of ${result.checked} ready.</b> Checks executable paths, ISO paths and launcher confidence; never runs or changes games.</p>`+
 (issues.length?issues.map(x=>`<div class="health-result"><strong>${esc(x.name)}</strong><small>${esc(x.issues.join('; '))}</small></div>`).join(''):'<p class="health-ok">All checked games look ready to launch.</p>');
 dialog('Game health','READ-ONLY SCAN',body);const summary=$('healthSummary');if(summary)summary.textContent=`${result.ready}/${result.checked} games ready · ${issues.length} need attention`;
}
function collectionPicker(g){const collections=state.collections||[];
 dialog('Your collections','ORGANIZE YOUR LIBRARY',`<p>Add <b>${esc(g.name)}</b> to an existing collection, or create a new one.</p>`+collections.map(c=>`<button class="option" data-collect="${esc(c.id)}"><span><b>${esc(c.name)}</b><small>${c.gameIds.includes(g.id)?'In collection · click to remove':'Add to collection'}</small></span><span>→</span></button>`).join('')+`<div class="dialog-row"><label>New collection</label><div style="display:flex;gap:8px"><input id="newCollectionName" maxlength="45" placeholder="e.g. Horror"><button class="add-btn" id="createCollection">Create</button></div></div>`);
 document.querySelectorAll('[data-collect]').forEach(el=>el.onclick=async()=>{const c=collections.find(x=>x.id===el.dataset.collect);const action=c.gameIds.includes(g.id)?'remove':'add';if(await safe(()=>api('/api/collection',{action,collectionId:c.id,gameId:g.id}))){closeDialog();await reload();notify('Collection updated.')}});
 $('createCollection').onclick=async()=>{const name=$('newCollectionName').value.trim();if(!name)return;const r=await safe(()=>api('/api/collection',{action:'create',name}));if(r){closeDialog();await reload();collectionPicker(game(g.id));}};
}
function manageCollections(){const cs=state.collections||[];dialog('Manage collections','YOUR CUSTOM SHELVES',`<p>Collections organize your existing games. Deleting a collection never deletes games.</p>${cs.map(c=>`<div class="collection-manager"><span><b>${esc(c.name)}</b><small>${c.gameIds.length} games</small></span><button class="btn-quiet" data-delete-collection="${esc(c.id)}">Delete</button></div>`).join('')||'<p>No collections yet.</p>'}<div class="dialog-row"><label>New collection</label><input id="newCollectionName" maxlength="45" placeholder="e.g. Party Games"></div><button class="btn-primary" id="createCollection">＋ Create</button>`);
 document.querySelectorAll('[data-delete-collection]').forEach(el=>el.onclick=async()=>{if(!confirm('Remove this collection? Game files stay untouched.'))return;if(await safe(()=>api('/api/collection',{action:'delete',collectionId:el.dataset.deleteCollection}))){closeDialog();await reload();manageCollections()}});
 $('createCollection').onclick=async()=>{if(await safe(()=>api('/api/collection',{action:'create',name:$('newCollectionName').value}))){closeDialog();await reload();manageCollections()}};
}
async function restoreSettingsDialog(){const list=await safe(()=>api('/api/backups'));if(!list)return;dialog('Restore settings','LOCAL RESTORE POINTS',`<p>Restores Elmos World settings, favorites, collections and emulator registrations. Game files and Steam data are untouched. Restart after restoring.</p>${list.length?list.map(x=>`<button class="option" data-restore="${esc(x.name)}"><b>${esc(x.name)}</b> <span>Restore →</span></button>`).join(''):'<p>No backups yet. Use Back up settings first.</p>'}`);
 document.querySelectorAll('[data-restore]').forEach(el=>el.onclick=async()=>{if(!confirm('Restore this settings backup? The current settings will be saved first.'))return;const r=await safe(()=>api('/api/restore',{name:el.dataset.restore}));if(r){closeDialog();await reload(true);notify('Settings restored. Restart Elmos World to apply everything.')}});
}
function renderShelves(){
 const live=state.games.filter(g=>!g.hidden&&!g.uncertain);
 const recent=live.filter(g=>g.lastPlayed).sort((a,b)=>(b.lastPlayed||0)-(a.lastPlayed||0)).slice(0,8);
 const favorites=live.filter(g=>g.favorite).slice(0,8);
 function paint(list,id,shelf){$(shelf).hidden=!list.length;$(id).innerHTML=list.map(g=>`<button class="shelf-tile" data-shelf-game="${esc(g.id)}"><div class="shelf-image">${g.art?.wide||g.art?.hero?`<img loading="lazy" decoding="async" src="${art(g,'wide')||art(g,'hero')}" alt="">`:cover(g)}</div><strong>${esc(g.name)}</strong></button>`).join('')}
 paint(recent,'recentCards','recentShelf');paint(favorites,'favoriteCards','favoriteShelf');
 document.querySelectorAll('[data-shelf-game]').forEach(el=>{el.onclick=()=>details(el.dataset.shelfGame);el.onfocus=()=>queuePreview(el.dataset.shelfGame);el.onpointerenter=()=>queuePreview(el.dataset.shelfGame)});
}
function setBackdrop(element,url){
 // Main image remains fully visible; a soft blurred fill handles aspect mismatches.
 const next=url||'';
 if(element.dataset.backdropUrl===next)return; // avoid costly duplicate paint/decode work
 element.dataset.backdropUrl=next;
 if(next)warmArt(next);
 element.style.setProperty('--game-background',next?'url("'+next+'")':'none');
 element.classList.toggle('has-backdrop',!!next);
}
function warmArt(url){
 if(!url)return;
 if(artPreloaded.has(url)){const record=artPreloaded.get(url);artPreloaded.delete(url);artPreloaded.set(url,record);return;}
 const img=new Image();img.decoding='async';img.src=url;artPreloaded.set(url,img);
 // A bounded LRU avoids accumulating hundreds of full-size hero images.
 while(artPreloaded.size>14)artPreloaded.delete(artPreloaded.keys().next().value);
}
let deckProgrammaticUntil=0,deckScrollTimer=null;
function selectGame(id,align=false){
 if(!visibleGames().some(g=>g.id===id))return;
 const changed=selected!==id;
 selected=id;
 localStorage.setItem('elmo-deck-selected',id);
 if(changed)renderFeatured();
 syncSelectedCard(align);
}
function queuePreview(id){clearTimeout(previewTimer);previewTimer=setTimeout(()=>selectGame(id,true),55)}
function syncSelectedCard(align=false){
 const root=$('gameCards');if(!root)return;
 const cards=[...root.querySelectorAll('.game-card')];
 let chosen=null;
 for(const card of cards){const on=card.dataset.g===selected;card.classList.toggle('selected',on);card.setAttribute('aria-selected',on?'true':'false');if(on)chosen=card;}
 if(chosen&&align){
  deckProgrammaticUntil=performance.now()+420;
  const center=chosen.getBoundingClientRect().left-root.getBoundingClientRect().left+root.scrollLeft+chosen.offsetWidth/2-root.clientWidth/2;
  root.scrollTo({left:Math.max(0,center),behavior:document.documentElement.dataset.motion==='reduced'?'instant':'smooth'});
 }
}
function selectCenteredCard(){
 if(performance.now()<deckProgrammaticUntil)return;
 const root=$('gameCards');if(!root||!root.clientWidth||screen!=='library')return;
 const center=root.getBoundingClientRect().left+root.clientWidth/2;
 let nearest=null,dist=Infinity;
 for(const card of root.querySelectorAll('.game-card')){
  const rect=card.getBoundingClientRect();const d=Math.abs((rect.left+rect.right)/2-center);
  if(d<dist){nearest=card;dist=d;}
 }
 if(nearest&&nearest.dataset.g!==selected)selectGame(nearest.dataset.g,false);
}
function updateBrowsePreview(g){
 const name=$('browsePreviewName');if(!name)return;
 name.textContent=g?.name||'Choose a game';
 $('browsePreviewPlatform').textContent=g?.platform||'Your library';
 const url=g?(art(g,'hero')||art(g,'wide')||art(g,'portrait')):'';
 $('browsePreviewArt').style.backgroundImage=url?'url("'+url+'")':'none';
 $('browsePreviewPlay').disabled=!g||g.uncertain;
 $('browsePreviewPlay').onclick=()=>g&&play(g);
 $('browsePreviewDetails').onclick=()=>g&&details(g.id);
}
function syncBrowsePreviewVisibility(){
 const bar=$('browsePreview'),hero=$('featuredHero');if(!bar||!hero)return;
 const bounds=hero.getBoundingClientRect();const shown=screen==='library'&&!modal&&bounds.top <= -(bounds.height*0.5);
 bar.classList.toggle('active',shown);bar.setAttribute('aria-hidden',shown?'false':'true');
}
window.addEventListener('scroll',syncBrowsePreviewVisibility,{passive:true});
window.addEventListener('resize',syncBrowsePreviewVisibility,{passive:true});
function renderFeatured(){
 const candidates=visibleGames();
 if(!candidates.length){selected=null;$('featuredTitle').textContent='Your world awaits.';$('featuredText').textContent='Add or restore games to begin.';$('featuredPlay').disabled=true;$('featuredDetails').disabled=true;return;}
 let g=candidates.find(x=>x.id===selected);
 if(!g){g=candidates[0];selected=g.id;localStorage.setItem('elmo-deck-selected',g.id);}
 const index=candidates.indexOf(g);
 $('featuredTitle').textContent=g.name;
 $('featuredText').textContent=g.uncertain?'Choose the correct launcher before playing.':g.type==='rom'?'Emulated game · cinematic handoff enabled.':g.playSeconds?`Continue playing · ${formatPlaytime(g.playSeconds)} tracked`:'Ready to play';
 const hero=art(g,'hero')||art(g,'wide');
 setBackdrop($('featuredHero'),hero);updateAmbient(hero);
 $('featuredPlay').disabled=g.uncertain|| (!!runningGameId && runningGameId!==g.id);$('featuredDetails').disabled=false;
 $('featureNumber').textContent=String(index+1).padStart(2,'0');
 $('featureTotal').textContent=String(candidates.length).padStart(2,'0');
 $('featuredPlay').textContent=runningGameId===g.id?'▶ Resume Game':runningGameId?'Another game is running':'▶ Play now';$('featuredPlay').onclick=()=>runningGameId===g.id?resumeTrackedGame():play(g);$('featuredDetails').onclick=()=>details(g.id);
 $('heroPreviewLabel').textContent='CENTER STAGE · '+g.name.toUpperCase();
 updateBrowsePreview(g);syncSelectedCard(false);
 candidates.slice(Math.max(0,index-2),index+3).forEach(x=>warmArt(art(x,'hero')||art(x,'wide')));
}

function renderReview(){const pending=state.games.filter(g=>g.uncertain&&!g.hidden);$('reviewList').innerHTML=pending.length?pending.map(g=>`<div class="list-row"><div><strong>${esc(g.name)}</strong><small>${g.type==='pc'?'Select the right game executable':'Verify emulator and ISO file'}</small></div><button class="add-btn" data-review="${esc(g.id)}">Configure →</button></div>`).join(''):'<div class="setting-note"><strong>Nothing needs attention.</strong><p>New game folders automatically appear in the library. Elmos World only asks you to choose a launcher when detection is uncertain.</p></div>';document.querySelectorAll('[data-review]').forEach(e=>e.onclick=()=>details(e.dataset.review))}
function renderHidden(){
 const hidden=state.games.filter(g=>g.hidden),box=$('hiddenGames');if(!box)return;
 $('deleteHiddenButton').disabled=!hidden.length;
 box.innerHTML=hidden.length?hidden.map(g=>`<div class="list-row"><div><strong>${esc(g.name)}</strong></div><button class="add-btn" data-restore="${esc(g.id)}">Restore</button></div>`).join(''):'<p class="muted">No hidden games.</p>';
 box.querySelectorAll('[data-restore]').forEach(el=>el.onclick=async()=>{if(await safe(()=>api('/api/hide',{id:el.dataset.restore,hidden:false})))await reload(true)});
}
function deleteHiddenDialog(){
 const hidden=state.games.filter(g=>g.hidden);if(!hidden.length){notify('No hidden games to delete.');return;}
 dialog('Delete hidden entries','LIBRARY CLEANUP',`<p>Select the hidden entries to forget. <b>Game files on your computer will not be deleted.</b> They will not return on the next rescan.</p><div class="hidden-select-actions"><button class="btn-quiet" id="hiddenSelectAll">Select all</button><button class="btn-quiet" id="hiddenSelectNone">Clear</button></div><div class="hidden-selection">${hidden.map((g,i)=>`<label class="hidden-select-row"><input type="checkbox" data-hidden-pick="${i}"><span>${esc(g.name)}</span></label>`).join('')}</div><div class="dialog-actions"><button class="danger-btn" id="hiddenDeleteConfirm" disabled>Delete selected from library</button><button class="btn-quiet" id="hiddenDeleteCancel">Cancel</button></div>`);
 const picks=[...document.querySelectorAll('[data-hidden-pick]')],confirmButton=$('hiddenDeleteConfirm');
 const update=()=>{const n=picks.filter(x=>x.checked).length;confirmButton.disabled=!n;confirmButton.textContent=n?`Delete ${n} selected from library`:'Choose games to delete';};
 picks.forEach(e=>e.onchange=update);
 $('hiddenSelectAll').onclick=()=>{picks.forEach(x=>x.checked=true);update()};
 $('hiddenSelectNone').onclick=()=>{picks.forEach(x=>x.checked=false);update()};
 $('hiddenDeleteCancel').onclick=closeDialog;
 confirmButton.onclick=async()=>{
  const ids=picks.filter(x=>x.checked).map(x=>hidden[Number(x.dataset.hiddenPick)].id);
  if(!ids.length)return;
  if(!confirm(`Forget ${ids.length} hidden game(s) from Elmos World? Game files will stay on your PC.`))return;
  confirmButton.disabled=true;
  const r=await safe(()=>api('/api/hidden-delete',{ids}));
  if(r){closeDialog();await reload(true);notify(r.message)}else update();
 };
 update();
}
// Separate GeForce NOW collection. No change to the local-games carousel.
let gfnSelected=localStorage.getItem('elmo-gfn-selected')||'',gfnCenterTimer=null;
const gfnItems=()=>state.gfnGames||[];
const gfnNormalize=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
function gfnArtFor(g,slot){
 const local=(state.games||[]).find(x=>gfnNormalize(x.name)===gfnNormalize(g.name));
 if(local){const url=art(local,slot==='portrait'?'portrait':'hero')||art(local,'wide');if(url)return url;}
 if(g.steamId){const id=encodeURIComponent(g.steamId);return slot==='portrait'?`https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/${id}/library_600x900.jpg`:`https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/${id}/library_hero.jpg`;}
 return '';
}
function gfnSelectedItem(){return gfnItems().find(x=>x.id===gfnSelected)||null;}
function gfnSelect(id,center=false){
 const g=gfnItems().find(x=>x.id===id);if(!g)return;
 gfnSelected=id;localStorage.setItem('elmo-gfn-selected',id);
 const hero=gfnArtFor(g,'hero');
 $('gfnHero').style.backgroundImage=hero?`linear-gradient(90deg,#0a1110 0%,rgba(10,17,16,.86) 27%,rgba(10,17,16,.13) 84%),url("${hero}")`:'';
 $('gfnHeroTitle').textContent=g.name;
 $('gfnHeroText').textContent=g.available?'GeForce NOW · Launch through your saved NVIDIA shortcut':'Shortcut missing · Reimport to play';
 $('gfnPlay').textContent=g.available?'▶ Play on GeForce NOW':'Shortcut unavailable';
 $('gfnPlay').disabled=!g.available;
 $('gfnPlay').onclick=()=>gfnLaunch(g);
 for(const card of $('gfnCards').querySelectorAll('.gfn-card')){
  const active=card.dataset.gfn===id;card.classList.toggle('active',active);card.setAttribute('aria-selected',active?'true':'false');
 }
 if(center){const card=[...$('gfnCards').querySelectorAll('.gfn-card')].find(x=>x.dataset.gfn===id);card?.scrollIntoView({inline:'center',block:'nearest',behavior:'smooth'});}
}
function renderGfn(){
 const games=gfnItems();$('gfnCount').textContent=`${games.length} game${games.length===1?'':'s'}`;
 const root=$('gfnCards');
 root.innerHTML=games.map(g=>{
 const image=gfnArtFor(g,'portrait');const monogram=esc(g.name.slice(0,2).toUpperCase());
 return `<button class="gfn-card" data-gfn="${esc(g.id)}"><span class="gfn-poster">${image?`<img loading="lazy" decoding="async" src="${esc(image)}" alt="" onerror="this.style.display='none'">`:''}<span class="gfn-monogram">${monogram}</span></span><strong>${esc(g.name)}</strong><small>${g.available?'CLOUD GAME · READY':'SHORTCUT MISSING'}</small></button>`;
 }).join('')||'<div class="gfn-empty">Nothing imported yet. Create a game shortcut in the GeForce NOW app, then import it here.</div>';
 for(const card of root.querySelectorAll('.gfn-card')){
  card.onfocus=()=>gfnSelect(card.dataset.gfn,false);
  card.onpointerenter=()=>gfnSelect(card.dataset.gfn,false);
  card.onclick=()=>{const game=gfnSelectedItem();if(game)gfnLaunch(game)};
 }
 if(games.length){if(!games.some(x=>x.id===gfnSelected))gfnSelected=games[0].id;gfnSelect(gfnSelected,false)}
 else{$('gfnHero').style.backgroundImage='';$('gfnHeroTitle').textContent='Your games. In the cloud.';$('gfnHeroText').textContent='Import shortcuts created by NVIDIA to build your separate cloud library.';$('gfnPlay').textContent='▶ Open GeForce NOW';$('gfnPlay').disabled=false;$('gfnPlay').onclick=gfnOpenApp;}
}
async function gfnOpenApp(){
 const provider=(state.platforms||[]).find(x=>x.name==='GeForce NOW'&&x.installed);
 if(provider){const r=await safe(()=>api('/api/open-platform',{name:'GeForce NOW'}));if(r)notify('Opening GeForce NOW…')}
 else notify('GeForce NOW was not detected at a standard installation path. Open its app and create per-game desktop shortcuts.',true);
}
async function gfnLaunch(g){
 if(!g?.available)return notify('This shortcut is missing. Import it again.',true);
 const r=await safe(()=>api('/api/gfn-launch',{id:g.id}));
 if(r){notify('Launching '+g.name+' through your NVIDIA shortcut…');if(window.pywebview?.api?.minimize)window.pywebview.api.minimize().catch(()=>{});}
}
async function gfnImport(){
 const path=await pick('gfn-shortcut');if(!path)return;
 const r=await safe(()=>api('/api/gfn-import',{path}));if(r){await reload(false);open('gfn');gfnSelect(r.id,true);notify('Cloud game imported. Use Find cover if it has no matching local artwork.');}
}
async function gfnDiscover(){
 const result=await safe(()=>api('/api/gfn-shortcuts'));if(!result)return;
 const candidates=result.shortcuts||[];
 if(!candidates.length){notify('No GeForce NOW desktop shortcuts were found. Create them inside the NVIDIA app, or use Import game shortcut.',true);return;}
 dialog('Discover GeForce NOW games','DESKTOP SHORTCUTS',`<p>Read-only scan of NVIDIA game shortcuts on your Desktop. Select what to import; no games will be launched during import.</p><div class="hidden-selection">${candidates.map((g,i)=>`<label class="hidden-select-row"><input type="checkbox" data-gfn-import="${i}"><span>${esc(g.name)}<small>${esc(g.path)}</small></span></label>`).join('')}</div><div class="dialog-actions"><button id="gfnImportSelected" class="btn-primary">Import selected games</button><button id="gfnCancelImport" class="btn-quiet">Cancel</button></div>`);
 $('gfnCancelImport').onclick=closeDialog;
 $('gfnImportSelected').onclick=async()=>{
  const selected=[...document.querySelectorAll('[data-gfn-import]:checked')].map(el=>candidates[Number(el.dataset.gfnImport)]);
  if(!selected.length)return notify('Choose at least one shortcut.',true);
  let count=0;for(const g of selected){const r=await safe(()=>api('/api/gfn-import',{path:g.path,name:g.name,title:g.name}));if(r)count++}
  closeDialog();await reload(false);open('gfn');notify(`${count} GeForce NOW games added.`);
 };
}
function gfnManage(){
 const games=gfnItems();
 dialog('Manage cloud library','GEFORCE NOW',`<p>All cloud games remain separate from your local game library. Removing one here never touches NVIDIA or Steam.</p>${games.map((g,i)=>`<div class="cloud-manage-row"><span><strong>${esc(g.name)}</strong><small>${esc(g.shortcut)}</small></span><button data-gfn-art="${i}" class="btn-quiet">Find cover</button><button data-gfn-rename="${i}" class="btn-quiet">Rename</button><button data-gfn-remove="${i}" class="danger-btn">Remove</button></div>`).join('')||'<p>No imported cloud shortcuts yet.</p>'}<div class="dialog-actions"><button class="btn-primary" id="gfnManageImport">＋ Import shortcut</button><button class="btn-quiet" id="gfnManageClose">Close</button></div>`);
 $('gfnManageImport').onclick=()=>{closeDialog();gfnImport()};$('gfnManageClose').onclick=closeDialog;
 document.querySelectorAll('[data-gfn-remove]').forEach(button=>button.onclick=async()=>{
  const g=games[Number(button.dataset.gfnRemove)];if(!confirm(`Remove ${g.name} from this cloud library? NVIDIA files are untouched.`))return;
  if(await safe(()=>api('/api/gfn-remove',{id:g.id}))){closeDialog();await reload(false);gfnManage();}
 });
 document.querySelectorAll('[data-gfn-rename]').forEach(button=>button.onclick=async()=>{
  const g=games[Number(button.dataset.gfnRename)],title=prompt('Name this cloud game',g.name);if(!title?.trim())return;
  if(await safe(()=>api('/api/gfn-rename',{id:g.id,title:title.trim()}))){closeDialog();await reload(false);gfnManage();}
 });
 document.querySelectorAll('[data-gfn-art]').forEach(button=>button.onclick=async()=>{
  const g=games[Number(button.dataset.gfnArt)];button.disabled=true;
  const r=await safe(()=>api('/api/gfn-art',{id:g.id}));
  if(r?.ok){closeDialog();await reload(false);gfnManage();notify('Found an exact Steam Store cover for '+g.name)}
  else{button.disabled=false;notify(r?.message||'Artwork lookup unavailable.',true)}
 });
}
function gfnMove(delta){const games=gfnItems();if(!games.length)return;const i=Math.max(0,games.findIndex(x=>x.id===gfnSelected));const g=games[Math.max(0,Math.min(games.length-1,i+delta))];gfnSelect(g.id,true);const c=[...$('gfnCards').querySelectorAll('.gfn-card')].find(x=>x.dataset.gfn===g.id);c?.focus({preventScroll:true});}
function renderEmulators(){const em=Object.entries(state.emulators||{});$('emulatorCards').innerHTML=em.length?em.map(([id,v])=>`<div class="list-row"><div><strong>${esc(v.name)}</strong><small>${esc(v.platform)} · ${esc(v.exe)}</small></div>${/xenia/i.test(v.exe)?`<button class="add-btn" data-xenia="${esc(id)}" title="Enable SDL input for PlayStation controllers">PS4 Controller</button>`:'<span class="tag">CONNECTED</span>'}</div>`).join(''):'<div class="setting-note">No emulators yet. Connect Xenia Canary for your SSX ISO.</div>';document.querySelectorAll('[data-xenia]').forEach(b=>b.onclick=async()=>{if(!confirm('Enable Xenia SDL controller support? Grove will back up the config first. Close Xenia before continuing.'))return;const r=await safe(()=>api('/api/xenia-sdl',{emulator:b.dataset.xenia}));if(r)notify(r.message)});$('romCards').innerHTML=state.games.filter(g=>g.type==='rom'&&!g.hidden).map(g=>`<div class="list-row"><div><strong>${esc(g.name)}</strong><small>${esc(g.gamefile)}</small></div><button class="add-btn" data-rom="${esc(g.id)}">View game →</button></div>`).join('')||'<div class="setting-note">No ISO or ROM entries yet. Add one above to launch through your configured emulator.</div>';document.querySelectorAll('[data-rom]').forEach(e=>e.onclick=()=>details(e.dataset.rom))}
function open(name){
 const previous=screen;
 if(previous!==name)menuSound();
 screen=name;document.documentElement.dataset.screen=name;
 document.querySelectorAll('.view').forEach(v=>v.classList.add('hidden'));
 $(name+'View').classList.remove('hidden');
 document.querySelectorAll('.rail-link').forEach(b=>b.classList.toggle('active',b.dataset.screen===name));
 $('locationTitle').textContent=({library:'YOUR LIBRARY',detail:'GAME DETAILS',queue:'NEEDS REVIEW',emulators:'EMULATORS',settings:'SETTINGS',activity:'YOUR ACTIVITY',gfn:'GEFORCE NOW'})[name];
 window.scrollTo({top:0,behavior:'instant'});
 if(name==='library' && previous!=='library'){
  // Restore deck position after the library becomes visible; never reset to item one.
  requestAnimationFrame(()=>syncSelectedCard(true));
 }
 syncBrowsePreviewVisibility();if(name==='activity'){renderActivity();refreshLaunchTimeline();}
}
function revealModalControl(target){
 // The controller deliberately uses preventScroll to avoid moving the full page.
 // Instead, scroll ONLY the dialog content so hidden controls become visible.
 const pane=$('dialogBody');
 if(!modal||!pane||!target||!pane.contains(target))return;
 const a=pane.getBoundingClientRect(),b=target.getBoundingClientRect();
 if(!a.height||!b.height)return;
 const margin=20;
 if(b.bottom>a.bottom-margin)pane.scrollTop+=b.bottom-(a.bottom-margin);
 else if(b.top<a.top+margin)pane.scrollTop-=a.top+margin-b.top;
}
function revealFocusedControl(target){
 if(!target||!target.getBoundingClientRect||target.closest?.('#gameCards'))return;
 if(modal){revealModalControl(target);return;}
 // Move the nearest scrollable ancestor first; do not jump the carousel or
 // replace the selected game. This works for long Settings/Emulators/Activity,
 // nested controller configuration panels and keyboard tab navigation.
 let child=target;
 for(let ancestor=target.parentElement;ancestor;ancestor=ancestor.parentElement){
  const style=getComputedStyle(ancestor);
  const vertical=/(auto|scroll)/.test(style.overflowY)&&ancestor.scrollHeight>ancestor.clientHeight+3;
  if(vertical){
   const viewport=ancestor.getBoundingClientRect(),rect=child.getBoundingClientRect(),margin=18;
   if(rect.bottom>viewport.bottom-margin)ancestor.scrollTop+=rect.bottom-viewport.bottom+margin;
   if(rect.top<viewport.top+margin)ancestor.scrollTop-=viewport.top+margin-rect.top;
  }
  child=ancestor;
 }
 // The normal library is deliberately viewport-bound; other sections are
 // allowed to scroll the document to keep the selected control fully visible.
 if(screen==='library'||screen==='detail')return;
 const r=target.getBoundingClientRect(),margin=24;
 if(r.bottom>window.innerHeight-margin)window.scrollBy({top:r.bottom-window.innerHeight+margin,behavior:'instant'});
 else if(r.top<margin)window.scrollBy({top:r.top-margin,behavior:'instant'});
}
document.addEventListener('focusin',e=>{if(e.target instanceof HTMLElement)revealFocusedControl(e.target);},true);
function dialog(title,kicker,html){$('dialogTitle').textContent=title;$('dialogKicker').textContent=kicker;$('dialogBody').innerHTML=html;$('dialogBody').scrollTop=0;$('dialogBackdrop').classList.remove('hidden');modal=true}
// Applies to keyboard focus and controller focus, including deep Configure items.
$('dialogBackdrop').addEventListener('focusin',e=>{revealModalControl(e.target)});
function closeDialog(){$('dialogBackdrop').classList.add('hidden');modal=false}
let launchTimer=null,sessionPollTimer=null,sessionState='idle',launchBusy=false;
let handoffInProgress=false,launchSequence=0;
let launchShield=false;
function setStagePhase(phase,desc){const x=$('launchPhase');if(x)x.textContent=phase;const line=$('launchPhaseDetail');if(line)line.textContent=desc||'';}
function stopLaunchPolling(){
 if(sessionPollTimer!==null)clearInterval(sessionPollTimer);
 sessionPollTimer=null;
}
function showLaunchStage(g){
 const stage=$('launchStage');stage.hidden=false;stage.classList.add('visible');
 $('launchTitle').textContent=g.name;
 $('launchSubtitle').textContent=g.type==='rom'?'Preparing emulator · '+(g.platform||'Game'):'Preparing your game';
 $('launchArt').style.backgroundImage='url("'+(art(g,'hero')||art(g,'wide')||art(g,'portrait'))+'")';
 $('launchStatus').textContent='Preparing your game…';setStagePhase('01 / PREPARING','Loading the cover and preparing the launch.');
 $('launchManual').hidden=true;
 $('launchControls').hidden=true;
 $('launchCancel').hidden=false;
}
function hideLaunchStage(keepMenuOnTop=false){
 if(launchShield){launchShield=false;if(!keepMenuOnTop)api('/api/shield',{enabled:false}).catch(()=>{});}
 clearTimeout(launchTimer);stopLaunchPolling();launchTimer=null;
 $('launchStage').classList.remove('visible');$('launchStage').hidden=true;
 $('launchControls').hidden=true;
 launchBusy=false;handoffInProgress=false;
}
async function handoffToGame(manual=false){
 if(sessionState!=='launching'||handoffInProgress)return;
 handoffInProgress=true;stopLaunchPolling();
 $('launchManual').hidden=true;
 $('launchStatus').textContent='Opening your game…';
 try{
  // This is a BEST-EFFORT foreground request. Windows may reject it even
  // though the detected game window is healthy and actually rendering.
  setStagePhase('03 / HANDOFF','Passing control to the detected game window.');
  const result=await api('/api/handoff',{});
  if(sessionState!=='launching')return;
  // Only proceed when a real game window exists. Readiness was verified by
  // the polling loop before this point, and may also be returned by the API.
  if(!result.focused && result.windowReady===false){
   $('launchStatus').textContent='Waiting for the game window. Open Game Controls or switch manually.';
   $('launchManual').hidden=false;
   $('launchControls').hidden=!runningGameId;
   return;
  }
  // Do NOT restore the startup shield on focus denial: that is exactly what
  // stranded Silent Hill 2 and Sekiro behind READY TO SWITCH.
  try{await api('/api/shield',{enabled:false});launchShield=false;}catch(e){}
  if(sessionState!=='launching')return;
  sessionState='playing';setGameInputSuspended(true,runningGameName);
  let minimized=false;
  if(window.pywebview?.api?.minimize){
   try{minimized=await window.pywebview.api.minimize()!==false;}catch(e){}
  }
  if(!minimized){
   document.body.classList.add('game-active-browser');
   if(!result.focused)notify('Game started. Use Alt+Tab to select its window.',true);
  }
  // Keep the cinematic cover visible right up until Elmos is minimized.
  hideLaunchStage();
 }catch(e){
  if(sessionState==='launching'){
   $('launchStatus').textContent='Launch needs attention. Open Game Controls or switch manually.';
   $('launchManual').hidden=false;
   $('launchControls').hidden=!runningGameId;
  }
 }finally{handoffInProgress=false}
}
async function play(g){
 if(!g||g.uncertain){notify('Choose a launcher first.',true);return}
 if(runningGameId){if(runningGameId===g.id)return resumeTrackedGame();notify('A game is already running. Resume or close it before starting another.',true);return}
 if(launchBusy)return;
 {
  try{const active=await api('/api/game-session');if(active.running){notify('A game is already running. Resume or close it before starting another.',true);return;}}catch(e){notify('Could not verify the active game session: '+e.message,true);return;}
 }
 launchBusy=true;sessionState='launching';handoffInProgress=false;
 const sequence=++launchSequence;
 const mode='direct';gameLaunchMode=mode;gameLaunchAt=performance.now();
 setGameInputSuspended(true,g.name);showLaunchStage(g);
 // Existing Elmos window serves as the launch shield. No secondary cover windows.
 if(mode==='direct'){try{const shield=await api('/api/shield',{enabled:true});launchShield=!!shield.enabled;}catch(e){launchShield=false;}}
 const result=await safe(()=>api('/api/launch',{id:g.id,mode}));
 setStagePhase('02 / LOADING','Preparing the game display.');
 if(sequence!==launchSequence)return;
 if(!result){sessionState='idle';setGameInputSuspended(false);hideLaunchStage();return}
 if(mode==='direct'){runningGameId=g.id;runningGameName=g.name;}
 let checks=0,polling=false;
 sessionPollTimer=setInterval(async()=>{
  if(polling||sessionState!=='launching'||handoffInProgress||sequence!==launchSequence)return;
  polling=true;
  try{
   checks++;
   if(mode==='steam'&&checks>=12){
    stopLaunchPolling();
    $('launchStatus').textContent='Steam is starting this game. Switch when its window appears.';
    $('launchManual').hidden=false;return;
   }
   const status=await api('/api/game-session');
   if(sessionState!=='launching'||sequence!==launchSequence)return;
   if(status.windowStable){
    stopLaunchPolling();
    await handoffToGame(false);
    return;
   }
   if(!status.running&&checks>2&&mode==='direct'){
    homeAfterGameExit();
    notify('Game closed. Returned to your library.');
    return;
   }
   if(checks>=65){
    stopLaunchPolling();
    $('launchStatus').textContent='Still waiting for the game window. You can switch manually or return to your library.';
    $('launchManual').hidden=false;
    $('launchControls').hidden=!runningGameId;
   }else {
    if(status.windowReady){setStagePhase('02 / STARTING', 'Getting everything ready for play.');
     $('launchStatus').textContent='Preparing your game…';}
    else $('launchStatus').textContent=checks>12?'Waiting for a game window…':'Starting the game process…';
   }
  }catch(e){
   stopLaunchPolling();$('launchStatus').textContent='Window detection unavailable. You can switch manually.';
   $('launchManual').hidden=false;
   $('launchControls').hidden=!runningGameId;
  }finally{polling=false}
 },160);
}
function openGameMenu(){
 if(!activeGameTitle||!runningGameId)return;
 // PS must work even when a game's window never passed Windows foreground
 // restrictions. The process is live; the menu does not depend on handoff.
 const cameFromUnfinishedLaunch=sessionState==='launching';
 // Keep the existing launcher window above the game while its PS menu opens.
 // Resume, Return Home and game exit explicitly release this temporary pin.
 hideLaunchStage(true);sessionState='menu';setGameInputSuspended(true,activeGameTitle);
 const menu=$('gameMenu');menu.hidden=false;menu.classList.add('visible');
 $('menuGameTitle').textContent=activeGameTitle;
 $('menuForceResume').hidden=true;
 if(cameFromUnfinishedLaunch)notify('The game is running. Resume, return home, or close it from here.');
 $('menuResume').focus({preventScroll:true});
}
function closeGameMenu(){
 // Re-focus the EXISTING game; never spawn another process.
 resumeTrackedGame();
}
window.elmoOpenGameMenu=openGameMenu;
window.elmoReceiveNativeMenu=async()=>{
 // Recover from a delayed/paused UI poll after the native window wakes.
 if(!runningGameId){
  try{
   const status=await api('/api/game-session');
   if(!status.running)return;
   runningGameId=status.gameId;runningGameName=status.gameName||'Game running';
   activeGameTitle=runningGameName;
  }catch(e){return;}
 }
 if(sessionState==='menu')return;
 if(sessionState==='idle'||sessionState==='library')sessionState='playing';
 openGameMenu();
};
window.elmoNativeReturnHome=()=>{
 // Native in-game panel intentionally leaves the running process alive.
 // The main Elmos window was minimized while playing; only Return Home
 // should wake its full interface. Never restart the game here.
 launchSequence++;
 hideLaunchStage(true);
 $('gameMenu').hidden=true;$('gameMenu').classList.remove('visible');
 sessionState='library';
 setGameInputSuspended(false);
 open('library');
 updateSessionPresentation();
};
window.elmoOnNativeGameExit=()=>{
 // Native process waiter wakes the WebView even if its timers were throttled.
 if(runningGameId||gameInputSuspended||sessionState==='launching'||sessionState==='menu')homeAfterGameExit();
};
$('menuResume').onclick=closeGameMenu;
$('menuForceResume').onclick=async()=>{
 if(!runningGameId)return;
 // Explicit user fallback: only minimize the launcher, never start a new game.
 $('gameMenu').hidden=true;$('gameMenu').classList.remove('visible');
 $('menuForceResume').hidden=true;
 sessionState='playing';setGameInputSuspended(true,runningGameName);
 // The old launcher window must no longer be topmost before minimizing.
 await api('/api/shield',{enabled:false}).catch(()=>{});
 if(window.pywebview?.api?.minimize){
  try{await window.pywebview.api.minimize();return;}catch(e){}
 }
 notify('Use Alt+Tab to select the running game.',true);
};
$('launchControls').onclick=openGameMenu;
$('menuLibrary').onclick=()=>{$('gameMenu').hidden=true;$('gameMenu').classList.remove('visible');sessionState='library';setGameInputSuspended(false);open('library');updateSessionPresentation();api('/api/shield',{enabled:false}).catch(()=>{});notify('Game still running · select Resume Game to return.');};
$('menuQuit').onclick=async()=>{
 const btn=$('menuQuit');btn.disabled=true;const original=btn.textContent;btn.textContent='Closing game…';
 try{
  const r=await api('/api/close-game',{});
  if(!r.closed){notify(r.message||'Game did not close.',true);return;}
  $('gameMenu').hidden=true;$('gameMenu').classList.remove('visible');
  homeAfterGameExit();notify(r.message||'Game closed.');
 }catch(e){notify('Game exit failed: '+e.message,true)}
 finally{btn.disabled=false;btn.textContent=original;}
};
$('launchManual').onclick=()=>handoffToGame(true);
$('launchCancel').onclick=()=>{launchSequence++;hideLaunchStage();sessionState='library';setGameInputSuspended(false);updateSessionPresentation();notify('Launch screen closed. If the game is running, use Resume Game.');};
async function details(id){closeViewer();
 const g=game(id);if(!g)return;
 selected=id;open('detail');
 $('detailTitle').textContent=g.name;
 $('detailPlatform').textContent=(g.platform||'PC')+' · '+(g.type==='rom'?'EMULATED':'WINDOWS GAME');
 $('detailDescription').textContent=g.uncertain?'Configure the game executable to play.':'Explore your game.';
 setBackdrop($('detailHero'),art(g,'hero')||art(g,'wide'));
 $('playSelected').disabled=g.uncertain || (!!runningGameId&&runningGameId!==g.id);
 $('playSelected').textContent=runningGameId===g.id?'▶ Resume Game':runningGameId?'Another game is running':'▶ Play Game';
 $('playSelected').onclick=()=>runningGameId===g.id?resumeTrackedGame():play(g);
 $('favoriteSelected').textContent=g.favorite?'♥':'♡';
 $('favoriteSelected').classList.toggle('selected',g.favorite);
 $('favoriteSelected').onclick=async()=>{const r=await safe(()=>api('/api/favorite',{id:g.id,favorite:!g.favorite}));if(r){await reload();details(id)}};
 $('configureSelected').onclick=()=>configure(g);
 $('detailConfigShortcut').onclick=()=>configure(g);
 $('detailFacts').innerHTML=`<span>PLATFORM<br><b>${esc(g.platform||'PC')}${g.type==='rom'?' · Emulated':''}</b></span><span>PLAYTIME<br><b>${esc(formatPlaytime(g.playSeconds||0))}</b></span>`;
 $('playSelected').focus({preventScroll:true});
 loadMetadata(g);
 loadGameGallery(g);
}
async function loadMetadata(g){
 const node=$('detailAbout');node.textContent='Finding the game overview…';
 if(!metadataCache[g.id]){
  metadataCache[g.id]=await safe(()=>api('/api/metadata?name='+encodeURIComponent(g.localMatch||g.name)+'&match='+encodeURIComponent(g.localMatch||'')))||{available:false};
 }
 if(selected!==g.id||screen!=='detail')return;
 const m=metadataCache[g.id];
 if(!m.available||!m.description){
  node.textContent='No verified game description is available yet. You can update the title or match artwork through Configure.';
  $('detailDescription').textContent=g.uncertain?'Configure this game before launching.':'Ready to play';
 }else{
  $('detailDescription').textContent=m.tagline||m.description;
  node.textContent=m.description;
 }
 $('detailFacts').innerHTML=[
  m.release?`<span>RELEASED<br><b>${esc(m.release)}</b></span>`:'',
  m.developer?`<span>STUDIO<br><b>${esc(m.developer)}</b></span>`:'',
  (m.genres||[]).length?`<span>GENRE<br><b>${esc(m.genres.join(' · '))}</b></span>`:'',
  `<span>PLATFORM<br><b>${esc(g.platform||'PC')}${g.type==='rom'?' · Emulated':''}</b></span>`,
  `<span>PLAYTIME<br><b>${esc(formatPlaytime(g.playSeconds||0))}</b></span>`,
  `<span>SESSIONS<br><b>${Number(g.playCount||0)} played</b></span>`
 ].join('');
}
// Media gallery is independent from descriptions. It is keyboard/controller
// accessible, and each item can be opened in a fullscreen media viewer.
let galleryRequest=0;
let galleryPoll=null;
let galleryItems=[];
let galleryRenderKey=null;
let viewerIndex=0;
let galleryCursor=0;
let viewerRestoreFocus=null;

function galleryFocusScroll(target){
 if(!target)return;
 const pane=$('detailShots');if(!pane)return;
 const r=pane.getBoundingClientRect(),c=target.getBoundingClientRect();
 if(c.right>r.right-10)pane.scrollLeft+=c.right-(r.right-10);
 if(c.left<r.left+10)pane.scrollLeft-=r.left+10-c.left;
}
function galleryMove(delta){
 const tiles=[...$('detailShots').querySelectorAll('.shot-tile')];
 if(!tiles.length)return;
 const active=tiles.indexOf(document.activeElement);
 const base=active>=0?active:galleryCursor;
 const candidate=Math.max(0,Math.min(tiles.length-1,base+delta));
 galleryCursor=candidate;
 tiles[candidate].focus({preventScroll:true});galleryFocusScroll(tiles[candidate]);
}
function showViewer(i){
 if(!galleryItems.length)return;
 viewerIndex=(i+galleryItems.length)%galleryItems.length;
 const item=galleryItems[viewerIndex];
 const video=$('viewerVideo'),image=$('viewerImage');
 video.pause();video.removeAttribute('src');video.load();
 video.hidden=true;image.hidden=true;image.removeAttribute('src');
 if(item.type==='trailer'){
  video.hidden=false;video.src=item.url;
  // User selected the trailer. Never autoplay while browsing the carousel.
  video.play().catch(()=>{});
 }else{image.hidden=false;image.src=item.url;image.alt=item.title;}
 $('viewerCounter').textContent=`${viewerIndex+1} / ${galleryItems.length}`;
 $('viewerTitle').textContent=item.title;
 $('mediaViewer').hidden=false;
 $('viewerClose').focus({preventScroll:true});
}
function openViewer(i){viewerRestoreFocus=document.activeElement;showViewer(i)}
function closeViewer(){
 const view=$('mediaViewer');if(view.hidden)return;
 view.hidden=true;
 const video=$('viewerVideo');video.pause();video.removeAttribute('src');video.load();
 $('viewerImage').removeAttribute('src');
 if(viewerRestoreFocus?.isConnected)viewerRestoreFocus.focus({preventScroll:true});
 viewerRestoreFocus=null;
}
function moveViewer(delta){showViewer(viewerIndex+delta)}
$('viewerPrev').onclick=()=>moveViewer(-1);
$('viewerNext').onclick=()=>moveViewer(1);
$('viewerClose').onclick=closeViewer;
$('mediaViewer').onclick=e=>{if(e.target===$('mediaViewer'))closeViewer()};
$('galleryPrev').onclick=()=>galleryMove(-1);
$('galleryNext').onclick=()=>galleryMove(1);
function paintGallery(g, result){
 const box=$('detailShots'),status=$('detailShotsStatus');
 if(!box||!status)return;
 const photos=result.screenshots||[];
 const nextKey=JSON.stringify([g.id,photos,result.trailer||{},result.status,result.refreshing,result.partial]);
 if(nextKey===galleryRenderKey)return;
 galleryRenderKey=nextKey;
 const trailer=result.trailer?.url?result.trailer:null;
 galleryCursor=0;
 galleryItems=[...(trailer?[{type:'trailer',url:trailer.url,title:trailer.title||'Official trailer'}]:[]),
  ...photos.map((url,i)=>({type:'image',url,title:`${g.name} · Screenshot ${i+1}`}))];
 if(galleryItems.length){
  box.innerHTML=galleryItems.map((item,i)=>item.type==='trailer'
   ?`<button class="shot-tile trailer-tile" type="button" data-index="${i}" aria-label="Play ${esc(item.title)}"><span class="trailer-play">▶</span><strong>WATCH TRAILER</strong><small>${esc(item.title)}</small></button>`
   :`<button class="shot-tile" type="button" data-index="${i}" aria-label="Expand screenshot ${i+1} of ${galleryItems.length}"><img src="${esc(item.url)}" loading="lazy" decoding="async" alt="${esc(item.title)}"></button>`).join('');
  box.querySelectorAll('.shot-tile').forEach(el=>{el.onclick=()=>openViewer(Number(el.dataset.index));el.onfocus=()=>{galleryCursor=Number(el.dataset.index);galleryFocusScroll(el)}});
  status.textContent=`${photos.length} SCREENSHOTS${trailer?' · TRAILER':''}${result.refreshing?' · UPDATING':''}${result.partial?' · RETRYING':''}`;
 }else if(result.status==='loading'||result.refreshing){
  box.innerHTML='<div class="gallery-empty">Finding official game media…</div>';
  status.textContent='CHECKING SOURCES';
 }else{
  box.innerHTML='<div class="gallery-empty"><strong>No game screenshots or trailers available</strong><small>Try Refresh Media in Configure, or import your own captures. Other game art remains available.</small></div>';
  status.textContent='NO MEDIA AVAILABLE';
 }
 $('galleryPrev').disabled=galleryItems.length<2;
 $('galleryNext').disabled=galleryItems.length<2;
}
async function loadGameGallery(g){
 clearTimeout(galleryPoll);
 const version=++galleryRequest;
 let tries=0;
 async function update(){
  if(version!==galleryRequest||selected!==g.id||screen!=='detail')return;
  try{
   const result=await api('/api/game-gallery?id='+encodeURIComponent(g.id));
   if(version!==galleryRequest||selected!==g.id||screen!=='detail')return;
   paintGallery(g,result);
   if(result.refreshing&&tries++<80)galleryPoll=setTimeout(update,900);
  }catch(e){
   if(version!==galleryRequest)return;
   paintGallery(g,{status:'error',screenshots:[]});
   $('detailShotsStatus').textContent='MEDIA UNAVAILABLE';
  }
 }
 galleryRenderKey=null;
 paintGallery(g,{status:'loading',screenshots:[]});
 await update();
}

async function configure(g){
 // Config is intentionally a popup, not an endlessly scrolling game page.
 const opts=g.candidates||[];
 const val=Number((state.launchProfiles||{})[g.id]?.readySeconds??(g.type==='rom'?5:0.9));
 const timing=[0.9,1.2,2,3,5,6,10,14,20];if(!timing.includes(val))timing.push(val);
 const choices=timing.sort((a,b)=>a-b).map(t=>`<option value="${t}" ${val===t?'selected':''}>${t}s${t===0.9?' · PC default (fast)':t===5?' · emulator default':''}</option>`).join('');
 const options=g.type==='pc'?opts.map((o,i)=>{
   const chosen=o.path===g.exe;
   return `<button class="option ${chosen?'active':''}" data-exe="${i}"><span><b>${esc(o.path.split(/[\\/]/).pop())}</b><small>${esc(o.path)} · ${Number(o.sizeMB||0)} MB${o.reasons?.length?' · '+esc(o.reasons.join(', ')):''}</small></span><span>${chosen?'CURRENT':i===0&&!g.uncertain?'RECOMMENDED':'SELECT'} →</span></button>`;
 }).join(''):'';
 dialog('Configure '+g.name,'GAME CONTROL',`
 <div class="config-scroll">
  ${g.type==='pc'?`<div class="config-block"><label>Display name</label><div class="config-inline"><input id="configName" maxlength="140" value="${esc(g.name)}"><button id="saveGameTitle" class="add-btn">Save title</button></div><small>${g.nameSource==='inner-folder'?'Identified from the game folder inside your download.':'Your editable library title.'}</small></div>`:''}
  <div class="config-block"><label>Game executable</label><small>Only game executables are suggested. Installers and maintenance tools are excluded.</small>
   ${g.type==='pc'?(options||'<p>No safe game executable identified.</p>'):`<div class="config-path">${esc(g.exe||'Emulator not configured')}</div><small>Manage emulators in the Emulators section.</small>`}
  </div>
  <div class="config-block"><label>Launch screen timing</label><select id="configTiming">${choices}</select><small>Your SSX/Xenia timing stays unchanged unless you update it here.</small></div>
  <div class="config-block"><label>Artwork & screenshots</label><div class="config-actions"><button id="configArtwork" class="btn-quiet">Match artwork</button><button id="configRefreshGallery" class="btn-quiet">Refresh media</button><button id="configImportGallery" class="btn-quiet">Import captures</button><button id="configCollections" class="btn-quiet">Collections</button><button id="configHealth" class="btn-quiet">Check game</button></div><small>Screenshots are cached locally. Games without an exact Steam Store listing can use screenshots imported from your own captures.</small></div>
  <div class="config-block"><label>Personal notes</label><textarea id="configNotes" rows="2" placeholder="Game notes…">${esc(g.note||'')}</textarea><button class="btn-quiet" id="configSaveNotes">Save notes</button></div>
  <div class="config-block"><label>Game compatibility</label>
   <small>Low-interference mode skips Windows foreground forcing on launch. This may improve difficult fullscreen games (such as Silent Hill 2). Your regular PS menu still works. Does not change graphics settings or suspend the game.</small>
   <label class="config-switch"><input type="checkbox" id="configLowImpact" ${g.lowImpactLaunch?'checked':''}><span>Low-interference launch mode</span></label>
  </div>
  <div class="config-block config-steam"><label>Steam Input fallback</label><p>Direct Play is always the default. Using Steam here applies to this launch only and never changes future Play presses.</p>
   <div class="config-actions"><button id="configSteamOnce" class="btn-quiet">Launch through Steam once</button><button id="configSteamImport" class="btn-quiet">${g.synced?'Steam shortcut connected':'Add shortcut to Steam (manual)'}</button></div>
  </div>
  <div class="config-block config-danger"><label>Game management</label>
   <small>Remove from your library without touching files, or move the entire installed PC game folder to the Windows Recycle Bin after explicit confirmation.</small>
   <div class="config-actions"><button id="configRemoveLibrary" class="btn-quiet">Remove from library</button><button id="configUninstallComputer" class="btn-quiet danger-btn" ${g.type!=='pc'?'disabled':''}>Uninstall from computer</button></div>
   ${g.type==='rom'?'<small>Emulator titles can be removed from the library. Their ISOs and emulator directories are protected from bulk deletion.</small>':''}
  </div>
 </div>`);
 const live=()=>document.getElementById('dialogBody')?.contains(document.getElementById('configTiming'));
 if($('saveGameTitle'))$('saveGameTitle').onclick=async()=>{const newName=$('configName').value.trim();const r=await safe(()=>api('/api/game-title',{id:g.id,title:newName}));if(r){closeDialog();await reload(true);metadataCache[g.id]=null;details(g.id);notify('Game title updated.')}};
 document.querySelectorAll('[data-exe]').forEach(b=>b.onclick=async()=>{const opt=opts[Number(b.dataset.exe)];if(!opt)return;const r=await safe(()=>api('/api/exe',{id:g.id,path:opt.path}));if(r){closeDialog();await reload(true);details(g.id);notify('Executable selected.')}});
 $('configTiming').onchange=async()=>{const r=await safe(()=>api('/api/launch-profile',{id:g.id,readySeconds:Number($('configTiming').value)}));if(r){state.launchProfiles=state.launchProfiles||{};state.launchProfiles[g.id]=r;notify('Launch timing saved.')}};
 $('configArtwork').onclick=()=>matchDialog(g);
 $('configRefreshGallery').onclick=async()=>{
  const response=await safe(()=>api('/api/refresh-gallery',{id:g.id}));
  if(response){notify(response.message||'Game media refresh requested.');loadGameGallery(g);}
 };
 $('configImportGallery').onclick=async()=>{
  const response=await safe(()=>api('/api/import-game-shots',{id:g.id}));
  if(response){notify(response.added?response.added+' screenshots imported.':'No screenshots selected.');loadGameGallery(g);}
 };

 $('configCollections').onclick=()=>collectionPicker(g);
 $('configHealth').onclick=()=>gameHealth(g.id);
 $('configSaveNotes').onclick=async()=>{const r=await safe(()=>api('/api/note',{id:g.id,note:$('configNotes').value}));if(r){g.note=$('configNotes').value;notify('Notes saved.')}};
 $('configLowImpact').onchange=async()=>{
  const enabled=$('configLowImpact').checked;
  const result=await safe(()=>api('/api/compatibility',{id:g.id,enabled}));
  if(result){g.lowImpactLaunch=enabled;notify(enabled?'Low-interference launch mode enabled.':'Standard game handoff restored.');}
  else $('configLowImpact').checked=!enabled;
 };
 $('configRemoveLibrary').onclick=()=>{
  dialog('Remove '+g.name+'?','LIBRARY MANAGEMENT',`<p>This hides ${esc(g.name)} from Elmos World. Game files are NOT changed. PC games can be restored in Settings → Hidden Games.</p><div class="dialog-actions"><button id="reallyRemoveLibrary" class="btn-primary">Remove from library</button><button id="cancelRemoveLibrary" class="btn-quiet">Cancel</button></div>`);
  $('cancelRemoveLibrary').onclick=closeDialog;
  $('reallyRemoveLibrary').onclick=async()=>{if(runningGameId){notify('Close the running game before removing an entry.',true);return;}const r=await safe(()=>api('/api/remove-library',{id:g.id}));if(r){closeDialog();await reload(true);open('library');notify('Removed from library. Files were not changed.');}};
 };
 $('configUninstallComputer').onclick=async()=>{
  const preview=await safe(()=>api('/api/uninstall-preview',{id:g.id}));if(!preview)return;
  dialog('Delete '+g.name+'?','PERMANENT GAME REMOVAL',`<div class="uninstall-warning"><strong>This permanently deletes the whole game folder.</strong><p>${esc(preview.warning)}</p><div class="config-path">${esc(preview.folder)}</div><p><b>This cannot be undone.</b> Only this exact selected game directory is eligible; the rest of your games library is protected.</p></div><div class="dialog-actions"><button id="confirmGameUninstall" class="danger-btn">Yes, delete the game permanently</button><button id="cancelGameUninstall" class="btn-quiet">No, keep game</button></div>`);
  $('cancelGameUninstall').onclick=closeDialog;
  $('confirmGameUninstall').onclick=async()=>{
   const button=$('confirmGameUninstall');button.disabled=true;
   const r=await safe(()=>api('/api/uninstall-confirm',{id:g.id,token:preview.token,confirmation:'DELETE_PERMANENTLY'}));
   if(r){closeDialog();await reload(true);open('library');notify(r.message)}else button.disabled=false;
  };
 };

 $('configSteamOnce').disabled=!g.synced;
 $('configSteamOnce').onclick=async()=>{
  if(!g.synced){notify('Import a shortcut first using the manual button.',true);return;}
  if(!confirm(`Launch ${g.name} through Steam once? Future Play presses will still use Direct Play.`))return;
  if(runningGameId){notify('Close or resume the current game first.',true);return;}
  const r=await safe(()=>api('/api/launch',{id:g.id,mode:'steam'}));if(r){closeDialog();notify('Steam launch requested. Future Play presses remain direct.');}
 };
 $('configSteamImport').disabled=!!g.synced;
 $('configSteamImport').onclick=async()=>{
  if(g.synced)return;
  if(!confirm('Manually create a Steam shortcut for this game? Steam must be fully closed. Game files will not be changed.'))return;
  const r=await safe(()=>api('/api/apply',{id:g.id}));if(r){closeDialog();await reload(true);notify('Steam shortcut added. Restart Steam to see it.');}
 };
}
async function matchDialog(g){if(!state.keyConfigured){notify('Add your SteamGridDB API key under Settings first.',true);open('settings');return}dialog('Find game artwork','STEAMGRIDDB',`<p>Search the game database and pick the correct title. Artwork is saved to Grove, not Steam.</p><div class="dialog-row"><label>Search game title</label><div style="display:flex;gap:10px"><input id="matchQuery" value="${esc(g.localMatch||g.name)}"><button class="add-btn" id="doSearch">Search</button></div></div><div id="matchResults">Searching...</div>`);$('doSearch').onclick=()=>searchMatches(g);$('matchQuery').onkeydown=e=>{if(e.key==='Enter')searchMatches(g)};await searchMatches(g)}
async function searchMatches(g){const box=$('matchResults');if(!box)return;box.textContent='Searching…';const matches=await safe(()=>api('/api/search?q='+encodeURIComponent($('matchQuery').value)));if(!box.isConnected)return;if(!matches){box.textContent='Search failed. Check network and API key.';return}box.innerHTML=matches.length?matches.map((m,i)=>`<button class="option" data-match="${i}"><span><b>${esc(m.name)}</b><small>Game ID ${esc(m.id)}</small></span><span>USE THIS →</span></button>`).join(''):'No matches found. Try another name.';document.querySelectorAll('[data-match]').forEach(b=>b.onclick=async()=>{let m=matches[Number(b.dataset.match)];b.disabled=true;b.textContent='Downloading artwork…';let r=await safe(()=>api('/api/library-match',{id:g.id,matchId:m.id,matchName:m.name}));if(r){closeDialog();await reload();metadataCache[g.id]=null;details(g.id);notify(`${r.downloaded} artwork images updated. Refreshing screenshots and trailers.${r.warnings.length?' Some styles unavailable.':''}`)}else b.disabled=false})}
async function pick(kind){const r=await safe(()=>api('/api/pick',{kind}));return r?.path||''}
async function addEmulator(){dialog('Connect an emulator','ONE-TIME SETUP',`<p>Choose the installed emulator once. Every game can use it afterward.</p><div class="dialog-row"><label>Emulator name</label><input id="emuName" value="Xenia Canary"></div><div class="dialog-row"><label>System</label><select id="emuSystem"><option>Xbox 360</option><option>GameCube / Wii</option><option>PlayStation 2</option><option>PlayStation 3</option><option>Other</option></select></div><div class="dialog-row"><label>Executable</label><div style="display:flex;gap:10px"><input id="emuExe" placeholder="Select emulator .exe"><button id="browseEmu" class="add-btn">Browse</button></div></div><div class="dialog-actions"><button class="btn-primary" id="saveEmulator">Connect emulator</button></div>`);$('browseEmu').onclick=async()=>{const p=await pick('emulator');if(p)$('emuExe').value=p};$('saveEmulator').onclick=async()=>{const r=await safe(()=>api('/api/emulator',{name:$('emuName').value,platform:$('emuSystem').value,exe:$('emuExe').value}));if(r){closeDialog();await reload();open('emulators');notify('Emulator connected. Add your ISO next.')}}}
async function addRom(){const em=Object.entries(state.emulators||{});if(!em.length){notify('Connect an emulator first.');return addEmulator()}dialog('Add an emulated game','ISO / ROM IMPORT',`<p>Pick your ISO or ROM, give it a name, and choose the emulator. For SSX select your .iso file.</p><div class="dialog-row"><label>Game title</label><input id="romTitle" value="SSX (2012)"></div><div class="dialog-row"><label>Game file</label><div style="display:flex;gap:10px"><input id="romPath" placeholder="Select an ISO or game file"><button class="add-btn" id="browseRom">Browse</button></div></div><div class="dialog-row"><label>Play with</label><select id="romEmulator">${em.map(([id,e])=>`<option value="${esc(id)}">${esc(e.name)} · ${esc(e.platform)}</option>`).join('')}</select></div><div class="dialog-actions"><button class="btn-primary" id="saveRom">Add game to Elmos World</button></div>`);$('browseRom').onclick=async()=>{let p=await pick('game');if(p)$('romPath').value=p};$('saveRom').onclick=async()=>{const r=await safe(()=>api('/api/rom',{name:$('romTitle').value,path:$('romPath').value,emulator:$('romEmulator').value}));if(r){closeDialog();await reload();details(r.id);notify('ISO game added. Ready for artwork matching.')}}}
function addGame(){dialog('Add to your collection','GROVE LIBRARY',`<p>Everything stays in its original folder. You only need to add the game once.</p><button class="option" id="addPc"><span><b>Windows PC game</b><small>Scan C:\Gaming\Games for new game folders</small></span>→</button><button class="option" id="addIso"><span><b>ISO / ROM</b><small>Play an emulated game like SSX using Xenia</small></span>→</button><button class="option" id="addEmu"><span><b>Connect an emulator</b><small>One-time setup for Xbox 360 and other systems</small></span>→</button>`);$('addPc').onclick=async()=>{closeDialog();await reload(true);open('queue');notify('Games scanned. Review any uncertain launchers.')};$('addIso').onclick=addRom;$('addEmu').onclick=addEmulator}
// Native SDL controller state is polled from localhost. Browser Gamepad API remains
// a fallback when SDL is unavailable. Focus moves geometrically between visible controls.
let prevPad={}, repeatAt=0, lastNav='', lastSource='', initialFocus=false;
function padControls(){
 if(!$('mediaViewer').hidden)return [...$('mediaViewer').querySelectorAll('button:not(:disabled)')];
 const view=modal?$('dialogBackdrop'):document.querySelector('.view:not(.hidden)');
 if(!view)return[];
 const pool=modal?[...view.querySelectorAll('button:not(:disabled),input,select,textarea')]:[
 ...document.querySelectorAll('.rail-link:not(:disabled)'),
 ...document.querySelectorAll('.topbar button:not(:disabled),.topbar input,.rail-tools button:not(:disabled),.rail-tools input'),
 ...view.querySelectorAll('button:not(:disabled),input,select,textarea')];
 return pool.filter(el=>el.getClientRects().length && el.getBoundingClientRect().width>0 && el.getBoundingClientRect().height>0);
}
// Right analog stick scrolls the current menu WITHOUT moving focus.
// D-pad / left-stick navigation stays unchanged. Only run while the launcher
// owns controller input; gameplay and the native PS-button menu are excluded.
let lastRightScrollTime=0;
function scrollWithRightStick(value,now=performance.now()){
 const axis=Number(value)||0;
 // The first resumed frame must not jump after a long game session.
 const elapsed=lastRightScrollTime?Math.max(.016,Math.min(.11,(now-lastRightScrollTime)/1000)):.07;
 lastRightScrollTime=now;
 if(gameInputSuspended||sessionState==='playing'||sessionState==='launching'||sessionState==='menu'||!$('mediaViewer').hidden)return false;
 const deadZone=.27;
 if(!Number.isFinite(axis)||Math.abs(axis)<=deadZone)return false;
 // Cubic response provides precise slow movement and fast travel at full tilt.
 const intensity=(Math.min(1,Math.abs(axis))-deadZone)/(1-deadZone);
 const pixels=Math.sign(axis)*(130+930*intensity*intensity)*elapsed;
 let pane=null;
 if(modal){pane=$('dialogBody');}
 else {
  // If the current screen contains a vertically scrollable panel, use it.
  const view=document.querySelector('.view:not(.hidden)');
  if(view){
   const focused=document.activeElement;
   for(let el=focused;el&&el!==view.parentElement;el=el.parentElement){
    if(el===document.body||el===document.documentElement)break;
    if(el.scrollHeight>el.clientHeight+4 && /auto|scroll/.test(getComputedStyle(el).overflowY)){pane=el;break;}
   }
   if(!pane&&view.scrollHeight>view.clientHeight+4 && /auto|scroll/.test(getComputedStyle(view).overflowY))pane=view;
  }
  if(!pane)pane=document.scrollingElement||document.documentElement;
 }
 if(!pane||pane.scrollHeight<=pane.clientHeight+2)return false;
 const before=pane.scrollTop;
 pane.scrollTop=Math.max(0,Math.min(pane.scrollHeight-pane.clientHeight,before+pixels));
 if(Math.abs(pane.scrollTop-before)>.1){document.body.classList.add('controller-active');return true;}
 return false;
}
function padFocusFirst(){const options=padControls();
 const preferred=screen==='library'?document.querySelector('#gameCards .game-card.selected')||document.querySelector('#gameCards .game-card'):screen==='detail'?$('playSelected'):null;
 (preferred&&options.includes(preferred)?preferred:options[0])?.focus({preventScroll:true});
 if(preferred?.classList.contains('game-card'))syncSelectedCard(true);
}
function navSpatial(dir){
 if(!$('mediaViewer').hidden){if(dir==='left')moveViewer(-1);else if(dir==='right')moveViewer(1);return;}
 if(screen==='detail'&&!modal&&['left','right'].includes(dir)&&document.activeElement?.closest('#detailShots')){galleryMove(dir==='right'?1:-1);return;}
 const opts=padControls();if(!opts.length)return;
 const active=document.activeElement;
 if(!opts.includes(active)){padFocusFirst();return}
 const isCard=el=>el.matches?.('.game-card,.shelf-tile');
 const ordered=[...document.querySelectorAll('#recentCards .shelf-tile,#favoriteCards .shelf-tile,#gameCards .game-card')].filter(el=>el.getClientRects().length);
 const currentRow=active.closest?.('#recentCards,#favoriteCards,#gameCards');
 if(currentRow && isCard(active)){
  const siblings=[...currentRow.querySelectorAll('.game-card,.shelf-tile')];
  let i=siblings.indexOf(active);
  if(dir==='left'||dir==='right'){
   const next=siblings[Math.max(0,Math.min(siblings.length-1,i+(dir==='right'?1:-1)))];
   next?.focus({preventScroll:true});if(next?.dataset.g)selectGame(next.dataset.g,true);
   return;
  }
  const rows=[...new Set(ordered.map(x=>x.parentElement))];
  const rowIndex=rows.indexOf(currentRow);
  const target=rows[rowIndex+(dir==='down'?1:-1)];
  if(target){
   const members=[...target.querySelectorAll('.game-card,.shelf-tile')];
   const next=members[Math.min(i,members.length-1)];
   next?.focus({preventScroll:true});if(next?.dataset.g)selectGame(next.dataset.g,true);
   return;
  }
  // At the top or bottom, do not send focus into an invisible scrolling region.
  if(dir==='up'){const hero=$('featuredPlay');hero?.focus({preventScroll:true});return}
 }
 // Return to the SAME selected cover after moving Up to Play or the command bar.
 // Never replace the user's selected game with the first item in the collection.
 if(dir==='down' && screen==='library' && !isCard(active)){
  const deck=$('gameCards');
  const target=[...(deck?.querySelectorAll('.game-card')||[])].find(c=>c.dataset.g===selected)
     ||deck?.querySelector('.game-card');
  if(target){target.focus({preventScroll:true});selectGame(target.dataset.g,true);return;}
 }
 if(dir==='down' && ordered.length && !isCard(active)){
  const first=ordered[0];first.focus({preventScroll:true});if(first.dataset.g)selectGame(first.dataset.g,true);return;
 }
 const r=active.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height/2;
 const choices=opts.filter(el=>el!==active).map(el=>{const b=el.getBoundingClientRect();const dx=b.left+b.width/2-cx,dy=b.top+b.height/2-cy;
  const along=dir==='right'?dx:dir==='left'?-dx:dir==='down'?dy:-dy;
  const across=dir==='left'||dir==='right'?Math.abs(dy):Math.abs(dx);
  return {el,along,score:along+across*2.5};
 }).filter(x=>x.along>3).sort((a,b)=>a.score-b.score);
 const next=choices[0]?.el;
 if(next){next.focus({preventScroll:true});if(next.dataset.g)selectGame(next.dataset.g,true);}
 else if(dir==='down'&&ordered.length){ordered[0].focus({preventScroll:true});ordered[0].scrollIntoView({block:'center',inline:'center',behavior:'auto'});}
}
const topTabs=['library','queue','emulators','gfn','activity','settings'];
function cycleTopNav(delta){
 if(modal)return;
 const current=topTabs.indexOf(screen);
 const idx=current<0?0:current;
 const next=topTabs[(idx+delta+topTabs.length)%topTabs.length];
 open(next);
 const tab=document.querySelector('.rail-link[data-screen="'+next+'"]');
 tab?.focus({preventScroll:true});
 document.body.classList.add('controller-active');
}
function padHandle(pad,source){
 if(pad)latestNative=pad;
 const connected=!!pad?.connected;
 $('controllerDot').style.background=connected?'#b4f5be':'#53645f';
 $('controllerLabel').textContent=connected?((pad.name||pad.id||'Controller')+' · '+(pad.mode||source)).slice(0,42):'Controller not detected';
 if(screen==='settings'&&performance.now()-diagLast>130){diagLast=performance.now();updateControllerDiagnostics(pad)}
 // Do not let background pad presses select games or change menus while playing.
 if(sessionState==='menu'&&document.hasFocus()&&pad?.connected){
  const buttons=Object.assign({},pad.buttons||{}),axes=pad.axes||[0,0];
  if(pad.mode==='raw SDL joystick'&&pad.rawButtons){for(const key of ['a','b'])buttons[key]=!!pad.rawButtons[controllerMap[key]];}
  const targets=[$('menuResume'),$('menuForceResume'),$('menuLibrary'),$('menuQuit')].filter(el=>!el.hidden);
  const d=buttons.down||(axes[1]||0)>.55?1:buttons.up||(axes[1]||0)<-.55?-1:0;
  const now=performance.now();
  if(d&&(lastNav!==String(d)||now>repeatAt)){
   let idx=targets.indexOf(document.activeElement);idx=Math.max(0,Math.min(targets.length-1,(idx<0?0:idx)+d));targets[idx].focus({preventScroll:true});repeatAt=now+190;
  }
  lastNav=String(d||'');
  if(buttons.a&&!prevPad.a)document.activeElement?.click?.();
  if(buttons.b&&!prevPad.b)closeGameMenu();
  prevPad={a:!!buttons.a,b:!!buttons.b};return;
 }
 if(gameInputSuspended||!document.hasFocus()){prevPad={};lastNav='';gateUntilRelease=true;return}
 if(!connected){document.body.classList.remove('controller-active');prevPad={};lastNav='';gateUntilRelease=true;lastRightScrollTime=0;return}
 const buttons=Object.assign({},pad.buttons||{}),axes=pad.axes||[0,0];
 if(pad.mode==='raw SDL joystick' && pad.rawButtons){for(const key of ['a','b','start','lb','rb'])buttons[key]=!!pad.rawButtons[controllerMap[key]];}

 const held=key=>!!buttons[key];
 if(gateUntilRelease){const anyHeld=Object.values(buttons).some(Boolean)||Math.abs(axes[0]||0)>.35||Math.abs(axes[1]||0)>.35||Math.abs(axes[3]||0)>.35;if(anyHeld)return;gateUntilRelease=false;prevPad={};}
 scrollWithRightStick(axes[3]||0);
 let dir=held('up')?'up':held('down')?'down':held('left')?'left':held('right')?'right':null;
 if(!dir&&Math.abs(axes[0]||0)>.55)dir=axes[0]>0?'right':'left';
 if(!dir&&Math.abs(axes[1]||0)>.55)dir=axes[1]>0?'down':'up';
 const now=performance.now();
 if(dir&&(dir!==lastNav||now>repeatAt)){document.body.classList.add('controller-active');menuSound();navSpatial(dir);repeatAt=now+(dir!==lastNav?260:155)}
 lastNav=dir;
 if(held('a')&&!prevPad.a){document.body.classList.add('controller-active');if(!padControls().includes(document.activeElement))padFocusFirst();else document.activeElement.click?.()}
 if(held('b')&&!prevPad.b){if(!$('mediaViewer').hidden)closeViewer();else if(modal)closeDialog();else if(screen==='detail')open('library');else if(screen!=='library')open('library');else padFocusFirst()}
 if(held('start')&&!prevPad.start){if(screen==='detail')$('playSelected').click();else if(screen==='library')$('featuredPlay').click()}
 if(held('lb')&&!prevPad.lb)cycleTopNav(-1);
 if(held('rb')&&!prevPad.rb)cycleTopNav(1);
 prevPad={a:held('a'),b:held('b'),start:held('start'),lb:held('lb'),rb:held('rb')};
}
function browserPad(){const p=Array.from(navigator.getGamepads?.()||[]).find(x=>x?.connected);if(!p)return null;
 const names={a:0,b:1,start:9,back:8,lb:4,rb:5,up:12,down:13,left:14,right:15};
 return {connected:true,name:p.id,axes:[p.axes[0]||0,p.axes[1]||0,p.axes[2]||0,p.axes[3]||0],buttons:Object.fromEntries(Object.entries(names).map(([n,i])=>[n,!!p.buttons[i]?.pressed]))};
}
window.addEventListener('mousemove',()=>document.body.classList.remove('controller-active'),{passive:true});
window.addEventListener('pointerdown',()=>document.body.classList.remove('controller-active'),{passive:true});
let lastMenuRequest=0;
let controllerBusy=false;
async function pollController(){if(controllerBusy)return;controllerBusy=true;
 try{const native=await api('/api/controller');if(native.menuRequested && native.menuRequested!==lastMenuRequest){
   lastMenuRequest=native.menuRequested;
   if(sessionState!=='menu')window.elmoReceiveNativeMenu();
  }padHandle(native.connected?native:(browserPad()||native),native.connected?'Native SDL':'Browser fallback')}
 catch(e){padHandle(browserPad(),'Browser')}
 finally{controllerBusy=false}
}
// Only listen to the first connected controller. No global gamepad hooks or game-input injection.
// Native SDL listens for the Guide button even when the window is minimized.
// Throttle HTTP input polling while playing, without blocking the PS menu.
function scheduleControllerPoll(){
 pollController().finally(()=>setTimeout(scheduleControllerPoll,sessionState==='playing'?650:85));
}
scheduleControllerPoll();
function updateControllerDiagnostics(p){
 if(!$('diagnosticStatus'))return;
 $('diagnosticStatus').textContent=p?.connected?`Connected: ${p.name||'Controller'} · ${p.mode||'Browser'} · ${p.devices?.length||1} device(s)`:`Not detected in Elmos World · ${p?.error||'Waiting for controller input'}`;
 const raw=p?.rawButtons||[];const axe=p?.rawAxes||p?.axes||[];const hats=p?.hats||[];
 $('diagnosticAxes').textContent=axe.length?axe.map((v,i)=>`Axis ${i}: ${Number(v).toFixed(2)}`).join('   ')+(hats.length?'   D-pad: '+JSON.stringify(hats[0]):''):'No axis data yet';
 $('diagnosticButtons').innerHTML=raw.length?raw.map((pressed,i)=>`<span class="diag-button ${pressed?'pressed':''}">${i}</span>`).join(''):'Press a controller button to test recognition';
}
function syncNativeMenuButtons(){api('/api/controller-map',{buttons:{a:controllerMap.a,b:controllerMap.b}}).catch(()=>{});}
function setupControllerEditor(){syncNativeMenuButtons();const options=Array.from({length:24},(_,i)=>`<option value="${i}">${i}</option>`).join('');
 for(const [key,id] of Object.entries({a:'mapA',b:'mapB',start:'mapStart',lb:'mapLb',rb:'mapRb',guide:'mapGuide'})){$(id).innerHTML=options;$(id).value=String(controllerMap[key]??controllerMapDefault[key]);}
 $('saveControllerMap').onclick=()=>{for(const [key,id] of Object.entries({a:'mapA',b:'mapB',start:'mapStart',lb:'mapLb',rb:'mapRb',guide:'mapGuide'}))controllerMap[key]=Number($(id).value);localStorage.setItem('elmo-controller-map',JSON.stringify(controllerMap));syncNativeMenuButtons();api('/api/guide-index',{index:controllerMap.guide}).then(()=>notify('Controller mapping saved. PS button will open the game menu.')).catch(e=>notify('PS mapping could not be saved: '+e.message,true));};
 $('resetControllerMap').onclick=()=>{controllerMap={...controllerMapDefault};localStorage.removeItem('elmo-controller-map');setupControllerEditor();api('/api/guide-index',{index:10}).then(()=>notify('PS4 button mapping restored.')).catch(e=>notify(e.message,true));};
 $('controllerRefresh').onclick=()=>pollController();
}
function applyVisualPreferences(){document.documentElement.dataset.theme=elmoTheme;document.documentElement.dataset.motion=elmoMotion;applyAtmosphere();$('themeChoice').value=elmoTheme;$('motionChoice').value=elmoMotion}
function fullscreenToggle(){if(window.pywebview?.api?.toggle_fullscreen)window.pywebview.api.toggle_fullscreen().catch(()=>{});else if(document.fullscreenElement)document.exitFullscreen?.();else document.documentElement.requestFullscreen?.().catch(()=>{});}
$('deleteHiddenButton').onclick=deleteHiddenDialog;
$('gfnImport').onclick=gfnImport;$('gfnDiscover').onclick=gfnDiscover;$('gfnManage').onclick=gfnManage;$('gfnPrev').onclick=()=>gfnMove(-1);$('gfnNext').onclick=()=>gfnMove(1);
$('logoHome').onclick=()=>open('library');document.querySelectorAll('.rail-link').forEach(b=>b.onclick=()=>open(b.dataset.screen));$('featuredDetails').onclick=()=>{};$('nextFeature').onclick=()=>moveCarousel(1);$('backToLibrary').onclick=()=>open('library');$('search').oninput=()=>{open('library');renderLibrary()};document.querySelectorAll('[data-sort]').forEach(b=>b.onclick=()=>{sort=b.dataset.sort;document.querySelectorAll('[data-sort]').forEach(x=>x.classList.toggle('active',x===b));renderLibrary()});$('rescan').onclick=async()=>{await reload(true);notify('Library refreshed. Existing games remain unchanged.')};$('queueRescan').onclick=async()=>{await reload(true);notify('Scan complete.')};$('addGame').onclick=addGame;$('newEmulator').onclick=addEmulator;$('newRom').onclick=addRom;$('closeDialog').onclick=closeDialog;$('dialogBackdrop').onclick=e=>{if(e.target===$('dialogBackdrop'))closeDialog()};window.addEventListener('keydown',e=>{if(e.key==='F11'){e.preventDefault();fullscreenToggle()}if(e.key==='Escape'){if(!$('mediaViewer').hidden){e.preventDefault();closeViewer();return;}if(sessionState==='menu'){e.preventDefault();closeGameMenu()}else if(modal)closeDialog();else if(screen==='detail')open('library')}if(!$('mediaViewer').hidden&&['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();moveViewer(e.key==='ArrowRight'?1:-1);return;}if(screen==='detail'&&!modal&&document.activeElement?.closest('#detailShots')&&['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();galleryMove(e.key==='ArrowRight'?1:-1);return;}if(e.key==='Backspace'&&document.activeElement.tagName!=='INPUT'&&document.activeElement.tagName!=='TEXTAREA'&&screen==='detail')open('library')});$('carouselPrev').onclick=()=>moveCarousel(-1);$('carouselNext').onclick=()=>moveCarousel(1);
function moveCarousel(delta){
 const list=visibleGames();if(!list.length)return;
 const index=Math.max(0,list.findIndex(g=>g.id===selected));
 const target=list[Math.max(0,Math.min(list.length-1,index+delta))];
 selectGame(target.id,true);
 const card=[...$('gameCards').querySelectorAll('.game-card')].find(el=>el.dataset.g===target.id);
 card?.focus({preventScroll:true});
}
$('gameCards').addEventListener('scroll',()=>{clearTimeout(deckScrollTimer);deckScrollTimer=setTimeout(selectCenteredCard,105)},{passive:true});
$('gameCards').addEventListener('wheel',e=>{if(screen!=='library')return;if(Math.abs(e.deltaY)>Math.abs(e.deltaX)){e.preventDefault();$('gameCards').scrollBy({left:e.deltaY*1.4,behavior:'auto'})}},{passive:false});
$('layoutChoice').onchange=()=>applyLayout($('layoutChoice').value);$('layoutToggle').onclick=()=>applyLayout('carousel');function applyLayout(value){libraryLayout='carousel';localStorage.setItem('elmo-layout','carousel');$('layoutChoice').value='carousel';renderLibrary();syncSelectedCard(true);notify('Home layout: single cinematic carousel')}
let updateReady=false;
async function checkElmosUpdate(){
 $('updateStatus').textContent='Checking GitHub Releases…';$('updateInstall').hidden=true;updateReady=false;
 try{const r=await api('/api/update-status');$('updateCurrent').textContent='v'+r.current;
  if(r.repository)$('updateRepository').value=r.repository;
  $('updateStatus').textContent=r.available?('Version '+r.latest+' available. '+r.message):r.message;
  if(r.lastAttempt?.state==='failed')$('updateStatus').textContent='Previous update failed: '+r.lastAttempt.detail+' — You can install the latest release from GitHub manually.';
  $('updateNotes').textContent=r.available?(r.notes||'No release notes supplied.'):'';
  updateReady=!!r.installable;$('updateInstall').hidden=!updateReady;
 }catch(e){$('updateStatus').textContent=e.message;}
}
$('updateSaveRepo').onclick=async()=>{const r=await safe(()=>api('/api/update-config',{repository:$('updateRepository').value}));if(r){notify('GitHub repository saved');await checkElmosUpdate();}};
$('updateCheck').onclick=checkElmosUpdate;
$('updateInstall').onclick=async()=>{if(!updateReady)return;
 if(!confirm('Download the verified update, back up settings, close Elmos World, and install the new version? Close any game first.'))return;
 const b=$('updateInstall');b.disabled=true;b.textContent='Downloading & verifying…';
 try{const result=await api('/api/update-install',{});if(result.restarting){$('updateStatus').textContent='Installer ready. Elmos World is closing for the update…';return;}}
 catch(e){notify(e.message,true);$('updateStatus').textContent=e.message;}
 b.disabled=false;b.textContent='Update & Restart';
};
setTimeout(checkElmosUpdate,2600);
$('saveSettings').onclick=async()=>{const changes={games_folder:$('gamesRoot').value};if($('artKey').value.trim())changes.api_key=$('artKey').value.trim();const r=await safe(()=>api('/api/settings',changes));if(r){$('artKey').value='';await reload();notify('Settings saved.')}};
$('resumeLibrary').onclick=resumeTrackedGame;
setupControllerEditor();pollController().then(()=>{if(latestNative?.guideIndex!==undefined && !localStorage.getItem('elmo-controller-map')){$('mapGuide').value=String(latestNative.guideIndex)}});applyVisualPreferences();$('themeChoice').onchange=()=>{elmoTheme=$('themeChoice').value;localStorage.setItem('elmo-theme',elmoTheme);applyVisualPreferences()};$('motionChoice').onchange=()=>{elmoMotion=$('motionChoice').value;localStorage.setItem('elmo-motion',elmoMotion);applyVisualPreferences()};
$('soundChoice').onchange=()=>{localStorage.setItem('elmo-sound',$('soundChoice').value);if($('soundChoice').value==='on'){if(!menuAudio&&window.AudioContext)menuAudio=new AudioContext();menuAudio?.resume?.().then(()=>menuSound()).catch(()=>{})}};
$('atmosphereChoice').onchange=()=>{localStorage.setItem('elmo-atmosphere',$('atmosphereChoice').value);applyAtmosphere();if(selected){const g=game(selected);if(g)updateAmbient(art(g,'hero')||art(g,'wide'))}};
$('tvModeChoice').onchange=()=>{localStorage.setItem('elmo-tv',$('tvModeChoice').value);applyAtmosphere()};
$('refreshLaunchLog').onclick=refreshLaunchTimeline;
$('refreshAllGalleries').onclick=async()=>{
 const result=await safe(()=>api('/api/refresh-all-galleries',{force:true}));
 if(result)notify('Checking screenshot sources for '+result.total+' library games. Images are saved locally as they become available.');
};
$('runHealthCheck').onclick=()=>gameHealth();$('manageCollections').onclick=manageCollections;$('backupSettings').onclick=async()=>{const r=await safe(()=>api('/api/backup',{}));if(r)notify('Settings backup created: '+r.name)};$('restoreSettings').onclick=restoreSettingsDialog;reload(true).finally(()=>{
 setTimeout(()=>$('splash').classList.add('done'),420);
 setTimeout(()=>$('splash').remove(),900);
 // Low-priority, one-at-a-time scan of the existing library. Never downloads
 // game executables or changes the saved matching/launch configuration.
 setTimeout(()=>api('/api/refresh-all-galleries',{force:false}).catch(()=>{}),1800);
});
})();
