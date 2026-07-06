(() => {
  "use strict";
  const STORAGE_KEY = "totp-repository-demo-v2";
  const DEMO_SECRET = "JBSWY3DPEHPK3PXP";
  const encoder = new TextEncoder();
  let tickTimer;
  let sharedItem;
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const views = { login: $("#login-view"), dashboard: $("#dashboard-view"), share: $("#share-view") };

  function makeId() { return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`; }
  function seededItems() {
    return [
      { id:makeId(),name:"亚马逊 TV 会员",code:"001",category:"亚马逊 TV",account:"demo001@example.com",expiry:"",secret:DEMO_SECRET,enabled:true },
      { id:makeId(),name:"亚马逊 TV 会员",code:"002",category:"亚马逊 TV",account:"demo002@example.com",expiry:"2026-08-09",secret:DEMO_SECRET,enabled:true },
      { id:makeId(),name:"ChatGPT Plus",code:"101",category:"ChatGPT",account:"team101@example.com",expiry:"2026-07-10",secret:DEMO_SECRET,enabled:true },
      { id:makeId(),name:"ChatGPT Team",code:"201",category:"ChatGPT",account:"team201@example.com",expiry:"2026-07-23",secret:DEMO_SECRET,enabled:true }
    ].map(withShareUrl);
  }
  function loadItems() { try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || seededItems(); } catch { return seededItems(); } }
  let items = loadItems();
  function saveItems() { localStorage.setItem(STORAGE_KEY, JSON.stringify(items)); }
  function showView(name) { Object.entries(views).forEach(([key,node]) => node.hidden = key !== name); }
  function cleanSecret(value) { return value.toUpperCase().replace(/[\s-]/g,"").replace(/=+$/g,""); }
  function decodeBase32(value) {
    const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ234567",secret=cleanSecret(value);
    if(!secret||[...secret].some(char=>!alphabet.includes(char))) throw new Error("请输入有效的 Base32 测试密钥");
    let bits=""; for(const char of secret) bits+=alphabet.indexOf(char).toString(2).padStart(5,"0");
    const bytes=[]; for(let index=0;index+8<=bits.length;index+=8) bytes.push(parseInt(bits.slice(index,index+8),2));
    if(!bytes.length) throw new Error("Base32 密钥太短"); return new Uint8Array(bytes);
  }
  async function generateTotp(secret,time=Date.now()) {
    const key=await crypto.subtle.importKey("raw",decodeBase32(secret),{name:"HMAC",hash:"SHA-1"},false,["sign"]);
    let counter=BigInt(Math.floor(time/1000/30)); const message=new Uint8Array(8);
    for(let index=7;index>=0;index--){message[index]=Number(counter&255n);counter>>=8n}
    const sign=new Uint8Array(await crypto.subtle.sign("HMAC",key,message)),offset=sign[sign.length-1]&15;
    const binary=((sign[offset]&127)<<24)|(sign[offset+1]<<16)|(sign[offset+2]<<8)|sign[offset+3];
    return String(binary%1000000).padStart(6,"0");
  }
  function spaced(code){return `${code.slice(0,3)} ${code.slice(3)}`}
  function base64UrlEncode(value){return btoa(unescape(encodeURIComponent(JSON.stringify(value)))).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/g,"")}
  function base64UrlDecode(value){const padded=value.replace(/-/g,"+").replace(/_/g,"/")+"===".slice((value.length+3)%4);return JSON.parse(decodeURIComponent(escape(atob(padded))))}
  function withShareUrl(item){const payload={name:item.name,code:item.code,secret:item.secret,nonce:item.nonce||makeId()};return{...item,nonce:payload.nonce,shareUrl:`${location.href.split("#")[0]}#share=${base64UrlEncode(payload)}`}}
  function toast(message){const node=$("#toast");node.textContent=message;node.classList.add("show");clearTimeout(toast.timer);toast.timer=setTimeout(()=>node.classList.remove("show"),1500)}
  async function copy(value,message){await navigator.clipboard.writeText(value);toast(message)}
  function categoryColor(category){return category==="ChatGPT"?"blue":category==="亚马逊 TV"?"green":"gray"}
  function memberStatus(item){if(!item.enabled)return{kind:"off",label:"已停用"};if(item.code==="101")return{kind:"warning",label:"5天到期"};return{kind:"on",label:item.expiry?"正常":"长期"}}

  function render(){
    $("#stat-total").textContent=items.length;$("#stat-active").textContent=items.filter(item=>item.enabled).length;
    const grid=$("#member-grid");grid.innerHTML="";
    items.forEach(item=>{
      const status=memberStatus(item),card=document.createElement("article");card.className="member-card";card.dataset.id=item.id;card.dataset.name=item.name.toLowerCase();card.dataset.code=item.code.toLowerCase();card.dataset.account=item.account.toLowerCase();card.dataset.category=item.category;card.dataset.status=status.kind;
      card.innerHTML=`<div class="member-card-head"><strong></strong><span class="category-badge ${categoryColor(item.category)}"></span></div><div class="member-card-details"><div class="member-field"><small>编号</small><span class="tag"></span></div><div class="member-field otp-field"><small>验证码</small><span class="otp-cell">—— ——</span></div><div class="member-field"><small>剩余时间</small><div class="countdown"><span>--</span>秒</div></div><div class="member-field"><small>会员状态</small><span class="member-status ${status.kind}">${status.label}</span>${item.expiry?`<span class="expiry-date">${item.expiry}</span>`:""}</div><div class="member-field share-field"><small>分享链接</small><div><button class="btn small copy">复制链接</button><span class="status ${item.enabled?"on":"off"}">${item.enabled?"有效":"已停用"}</span></div></div></div>${item.account?`<div class="member-account"><span>登录账号</span></div>`:""}<div class="row-actions member-card-actions"><button class="btn small ghost edit">编辑</button><button class="btn small ${item.enabled?"danger":"primary"} toggle">${item.enabled?"停用":"启用"}</button><button class="btn small ghost rotate">重置链接</button></div>`;
      card.querySelector(".member-card-head strong").textContent=item.name;card.querySelector(".category-badge").textContent=item.category;card.querySelector(".tag").textContent=item.code;if(item.account)card.querySelector(".member-account").append(item.account);
      const copyButton=card.querySelector(".copy");copyButton.dataset.copy=item.shareUrl;copyButton.onclick=()=>copy(item.shareUrl,"分享链接已复制");card.querySelector(".edit").onclick=()=>toast("演示版请删除后重新添加");card.querySelector(".toggle").onclick=()=>{item.enabled=!item.enabled;saveItems();render()};card.querySelector(".rotate").onclick=()=>{const rotated=withShareUrl({...item,nonce:makeId()});item.nonce=rotated.nonce;item.shareUrl=rotated.shareUrl;saveItems();toast("分享链接已重置")};grid.appendChild(card);
    });
    applyFilters();startTicks();
  }
  function applyFilters(){const query=$("#member-search").value.trim().toLowerCase(),category=$("#category-filter").value,status=$("#status-filter").value;let visible=0;$$('.member-card').forEach(card=>{const matches=(!query||`${card.dataset.name} ${card.dataset.code} ${card.dataset.account}`.includes(query))&&(!category||card.dataset.category===category)&&(!status||card.dataset.status===status);card.hidden=!matches;if(matches)visible++});$("#visible-count").textContent=visible;$("#empty-state").hidden=visible!==0}
  async function updateCodes(){const remaining=30-(Math.floor(Date.now()/1000)%30);for(const item of items){const card=document.querySelector(`.member-card[data-id="${CSS.escape(item.id)}"]`);if(card){card.querySelector(".otp-cell").textContent=spaced(await generateTotp(item.secret));card.querySelector(".countdown span").textContent=remaining}}if(sharedItem){$("#shared-otp").textContent=spaced(await generateTotp(sharedItem.secret));$("#shared-remaining").textContent=remaining;$("#share-countdown").style.setProperty("--progress",`${remaining*12}deg`)}}
  function startTicks(){clearInterval(tickTimer);updateCodes();tickTimer=setInterval(updateCodes,1000)}
  function applyTheme(preference){const dark=preference==="dark"||(preference==="system"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.dataset.theme=dark?"dark":"light";$$('[data-theme-value]').forEach(button=>button.classList.toggle("selected",button.dataset.themeValue===preference));$("[data-theme-label]").textContent={light:"浅色",dark:"深色",system:"跟随系统"}[preference];$("[data-theme-icon]").textContent={light:"☀",dark:"☾",system:"▣"}[preference]}
  $$('[data-theme-value]').forEach(button=>button.onclick=()=>{localStorage.setItem("theme",button.dataset.themeValue);applyTheme(button.dataset.themeValue);button.closest("details").removeAttribute("open")});applyTheme(localStorage.getItem("theme")||"system");
  $("#login-form").onsubmit=event=>{event.preventDefault();const valid=$("#login-user").value.trim()==="admin"&&$("#login-password").value==="demo123";$("#login-error").hidden=valid;if(valid){sessionStorage.setItem("totp-demo-session","1");showView("dashboard");render()}};
  $("#logout-button").onclick=()=>{sessionStorage.removeItem("totp-demo-session");showView("login")};
  $$('[data-demo-disabled]').forEach(link=>link.onclick=event=>{event.preventDefault();toast("在线演示暂不包含此页面")});
  [$("#member-search"),$("#category-filter"),$("#status-filter")].forEach(control=>{control.addEventListener("input",applyFilters);control.addEventListener("change",applyFilters)});
  $("#open-add").onclick=()=>{$("#add-form").reset();$("#add-error").hidden=true;$("#add-dialog").showModal()};$$('[data-close-dialog]').forEach(button=>button.onclick=()=>$("#add-dialog").close());
  $("#add-form").onsubmit=async event=>{event.preventDefault();const error=$("#add-error");try{const secret=cleanSecret($("#field-secret").value);await generateTotp(secret);const item=withShareUrl({id:makeId(),name:$("#field-name").value.trim(),code:$("#field-code").value.trim(),category:$("#field-category").value,account:$("#field-account").value.trim(),expiry:$("#field-expiry").value,notes:$("#field-notes").value,secret,enabled:true});items.unshift(item);saveItems();render();$("#add-dialog").close();await copy(item.shareUrl,"已保存，分享链接已复制")}catch(reason){error.textContent=reason.message||"无法添加密钥";error.hidden=false}};
  $("#copy-shared-code").onclick=()=>copy($("#shared-otp").textContent.replace(/\s/g,""),"验证码已复制");
  function route(){clearInterval(tickTimer);sharedItem=null;if(location.hash.startsWith("#share=")){showView("share");try{sharedItem=base64UrlDecode(location.hash.slice(7));if(!sharedItem.name||!sharedItem.code||!sharedItem.secret)throw new Error();$("#shared-name").textContent=sharedItem.name;$("#shared-number").textContent=`编号 ${sharedItem.code}`;startTicks()}catch{$("#share-card").innerHTML=`<h1>演示链接已更新</h1><p class="muted">请返回演示后台重新复制分享链接。</p><a class="btn primary wide" href="${location.href.split("#")[0]}">返回演示首页</a>`}}else if(sessionStorage.getItem("totp-demo-session")==="1"){showView("dashboard");render()}else showView("login")}
  window.addEventListener("hashchange",route);route();
})();
