// Migration-only service worker. Older installed versions cached the app shell.
// Retire that cache and unregister this worker. Until tabs are reloaded, use the
// network exclusively so stale HTML/JavaScript never masks corrected inspections.
const CACHE_PREFIX='sf-food-check-';
self.addEventListener('install',()=>{self.skipWaiting();});
self.addEventListener('activate',event=>{
  event.waitUntil((async()=>{
    const keys=await caches.keys();
    await Promise.all(keys.filter(key=>key.startsWith(CACHE_PREFIX)).map(key=>caches.delete(key)));
    await self.clients.claim();
    await self.registration.unregister();
  })());
});
self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET')return;
  const url=new URL(request.url);
  if(url.origin!==self.location.origin)return;
  event.respondWith(fetch(request,{cache:'no-store'}));
});
