"""Self-contained player served locally or uploaded alongside nowplaying.json."""
PLAYER_HTML = r'''<!doctype html>
<html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mi estación · En vivo</title><style>
:root{color-scheme:light dark}body{margin:0;background:Canvas;color:CanvasText;font:16px system-ui;min-height:100vh;display:grid;place-items:center}
main{width:min(88vw,480px);padding:28px;background:Canvas;border:1px solid GrayText;border-radius:4px;text-align:center}
img{width:min(75vw,300px);height:300px;object-fit:contain;border-radius:2px;background:Canvas}
h1{font-size:22px}h2{font-size:26px;margin-bottom:8px}p{color:CanvasText}audio{width:100%;margin-top:20px}
small{display:block;color:CanvasText;margin-top:14px}img[hidden]{display:none}
</style><main><h1 id="station">Mi estación</h1><img id="cover" alt="Carátula o logo de la estación" hidden>
<h2 id="title">Conectando…</h2><p id="artist"></p><p id="album"></p><audio id="audio" controls preload="none"></audio>
<small id="status">Actualizando información</small></main><script>
const el=id=>document.getElementById(id);let latest=null,lastImage='';
function imageUrl(value){if(!value)return '';if(/^artwork-[a-f0-9]+\.(png|jpg|webp)$/.test(value))return value;
try{let u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password?u.href:''}catch{return ''}}
function paint(){if(!latest)return;let age=(Date.now()-Date.parse(latest.updated_at))/1000;
let fresh=Number.isFinite(age)&&age>=-60&&age<=latest.stale_seconds;
let music=fresh&&latest.is_music===true;
el('station').textContent=latest.station;document.title=latest.station+' · En vivo';
el('title').textContent=music?latest.title:(fresh?(latest.display_message||'Sin información musical'):latest.idle_message);
el('artist').textContent=music?latest.artist:latest.slogan;el('album').textContent=music?latest.album:'';
el('status').textContent=fresh?'En vivo · información actualizada':'Información musical no disponible';
let src=imageUrl(music?(latest.artwork_url||latest.artwork_file):(latest.logo_url||latest.logo_file));
if(src!==lastImage){lastImage=src;el('cover').hidden=!src;if(src)el('cover').src=src;else el('cover').removeAttribute('src')}
if(latest.stream_url&&el('audio').getAttribute('src')!==latest.stream_url){try{let u=new URL(latest.stream_url);if(['https:','http:'].includes(u.protocol))el('audio').src=u.href}catch{}}
}
async function refresh(){try{let r=await fetch('nowplaying.json?_='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error();latest=await r.json();paint()}
catch{paint();if(!latest){el('title').textContent='Estación en vivo';el('status').textContent='Sin información musical'}}
finally{setTimeout(refresh,2000)}}
el('cover').onerror=()=>{el('cover').hidden=true};setInterval(paint,1000);refresh();
</script></html>'''
