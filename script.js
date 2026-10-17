const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
// Storage keys are declared before initial rendering to avoid temporal-dead-zone errors.
const FOCUS_KEY="talaba_focus_sessions_v1";
const QUIZ_KEY="talaba_quiz_results_v1";
const LIBRARY_KEY="talaba_library_v1";
const PROFILE_KEY="talaba_profile_v1";
const SETTINGS_KEY="talaba_settings_v1";
const toast = (message) => {
  const el=$("#toast"); if(!el) return;
  el.textContent=message; el.classList.add("show");
  clearTimeout(window.toastTimer); window.toastTimer=setTimeout(()=>el.classList.remove("show"),2600);
};
const pages = ["home","assistant","exams","schedule","library","focus","settings","help","account"];
function showPage(name){
  if(!pages.includes(name)) name="home";
  $$(".page").forEach(p=>p.classList.toggle("active",p.id===`page-${name}`));
  $$(".nav-item").forEach(b=>b.classList.toggle("active",b.dataset.page===name));
  window.scrollTo({top:0,behavior:"smooth"});
  if(name==="assistant") setTimeout(()=>$("#chatInput")?.focus(),150);
}
$$(".nav-item").forEach(btn=>btn.addEventListener("click",()=>showPage(btn.dataset.page)));
$$("[data-go]").forEach(btn=>btn.addEventListener("click",()=>showPage(btn.dataset.go)));
$$("[data-scroll]").forEach(btn=>btn.addEventListener("click",()=>{$($(btn).dataset.scroll)?.scrollIntoView({behavior:"smooth",block:"center"});}));

// Demo-only local account flow. Real authentication must be implemented by the backend.
const AUTH_KEY="talaba_demo_account_v1";
const SESSION_KEY="talaba_demo_session_v1";
const levelNames={middle:"التعليم المتوسط",secondary:"التعليم الثانوي",university:"الجامعة",master:"الماستر",other:"مستوى آخر"};
function yearOptions(level){
  if(level==="middle")return [{value:"1",label:"السنة الأولى متوسط"},{value:"2",label:"السنة الثانية متوسط"},{value:"3",label:"السنة الثالثة متوسط"},{value:"4",label:"السنة الرابعة متوسط"}];
  if(level==="secondary")return [{value:"1",label:"السنة الأولى ثانوي"},{value:"2",label:"السنة الثانية ثانوي"},{value:"3",label:"السنة الثالثة ثانوي"}];
  if(level==="university")return [{value:"1",label:"السنة الأولى ليسانس (L1)"},{value:"2",label:"السنة الثانية ليسانس (L2)"},{value:"3",label:"السنة الثالثة ليسانس (L3)"}];
  if(level==="master")return [{value:"1",label:"السنة الأولى ماستر (M1)"},{value:"2",label:"السنة الثانية ماستر (M2)"}];
  return [{value:"1",label:"مستوى آخر"}];
}
function levelLabel(user){
  if(!user?.level)return "لم يُحدّد المستوى";
  const options=yearOptions(user.level), year=options.find(x=>x.value===String(user.year))?.label||"";
  return `${levelNames[user.level]||"مستوى دراسي"}${year?" — "+year:""}${user.specialty?" — "+user.specialty:""}`;
}
function updateYearOptions(levelEl,yearEl){
  if(!levelEl||!yearEl)return;
  const prior=yearEl.value;yearEl.innerHTML=yearOptions(levelEl.value).map(x=>`<option value="${x.value}">${x.label}</option>`).join("");
  if([...yearEl.options].some(o=>o.value===prior))yearEl.value=prior;
}
const getAccount=()=>{try{return JSON.parse(localStorage.getItem(AUTH_KEY)||"null")}catch{return null}};
const getSession=()=>{try{return JSON.parse(sessionStorage.getItem(SESSION_KEY)||"null")}catch{return null}};
function setAuthMode(mode){
  const registering=mode==="register";
  $("#loginForm").classList.toggle("hidden",registering);
  $("#registerForm").classList.toggle("hidden",!registering);
  $("#authTitle").textContent=registering?"إنشاء حساب جديد":"مرحباً بعودتك";
  $("#authSubtitle").textContent=registering?"أنشئ حسابك للبدء في تنظيم دراستك":"سجّل الدخول لمتابعة رحلتك الدراسية";
}
function showAuth(){ $("#authScreen").classList.remove("is-hidden"); $("#appShell").classList.add("auth-locked"); }
function hideAuth(){ $("#authScreen").classList.add("is-hidden"); $("#appShell").classList.remove("auth-locked"); }
function applyUser(user){
  const name=user?.name||"طالب";
  $("#welcomeName").textContent=name;
  $("#profileName").textContent=name;
  $("#accountEmail").textContent=user?.email||"—";
  $("#joinDate").textContent=user?.joined||"اليوم";
  const level=levelLabel(user);
  if($("#accountLevel"))$("#accountLevel").textContent=level;
  if($("#profileLevelSummary"))$("#profileLevelSummary").textContent=level;
}
async function hashPassword(password){
  if(window.crypto?.subtle){
    const bytes=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(password));
    return [...new Uint8Array(bytes)].map(b=>b.toString(16).padStart(2,"0")).join("");
  }
  // Fallback only for local demo compatibility; do not use this approach in production.
  return btoa(unescape(encodeURIComponent(password)));
}
$("#showRegister").addEventListener("click",()=>setAuthMode("register"));
$("#showLogin").addEventListener("click",()=>setAuthMode("login"));
$("#registerLevel")?.addEventListener("change",()=>updateYearOptions($("#registerLevel"),$("#registerYear")));
updateYearOptions($("#registerLevel"),$("#registerYear"));
$("#registerForm").addEventListener("submit",async e=>{
  e.preventDefault();
  const name=$("#registerName").value.trim(), email=$("#registerEmail").value.trim().toLowerCase();
  const password=$("#registerPassword").value, confirm=$("#registerConfirm").value;
  const level=$("#registerLevel").value, year=$("#registerYear").value;
  if(password.length<6){toast("كلمة المرور يجب أن تتكون من 6 أحرف على الأقل");return}
  if(password!==confirm){toast("كلمتا المرور غير متطابقتين");return}
  const current=getAccount();
  if(current?.email===email){toast("يوجد حساب بهذا البريد؛ سجّل الدخول");setAuthMode("login");$("#loginEmail").value=email;return}
  const user={name,email,level,year,passwordHash:await hashPassword(password),joined:new Date().toLocaleDateString("ar-DZ",{year:"numeric",month:"long",day:"numeric"})};
  localStorage.setItem(AUTH_KEY,JSON.stringify(user));
  sessionStorage.setItem(SESSION_KEY,JSON.stringify({email}));
  applyUser(user);hideAuth();toast("تم إنشاء الحساب التجريبي بنجاح");e.target.reset();
});
$("#loginForm").addEventListener("submit",async e=>{
  e.preventDefault();
  const email=$("#loginEmail").value.trim().toLowerCase(), password=$("#loginPassword").value;
  const user=getAccount();
  if(!user||user.email!==email||user.passwordHash!==await hashPassword(password)){
    toast("البريد الإلكتروني أو كلمة المرور غير صحيحة");return;
  }
  sessionStorage.setItem(SESSION_KEY,JSON.stringify({email}));
  applyUser(user);hideAuth();toast("تم تسجيل الدخول بنجاح");e.target.reset();
});
$("#logoutBtn").addEventListener("click",()=>{sessionStorage.removeItem(SESSION_KEY);showAuth();setAuthMode("login");toast("تم تسجيل الخروج")});
const account=getAccount(), session=getSession();
if(account&&session?.email===account.email){applyUser(account);hideAuth()}else{showAuth();setAuthMode("login")}

$("#fullscreen").addEventListener("click",async()=>{try{if(!document.fullscreenElement) await document.documentElement.requestFullscreen();else await document.exitFullscreen()}catch{toast("ملء الشاشة غير متاح في هذا المتصفح")}});
$("#notifications").addEventListener("click",()=>toast("لا توجد إشعارات جديدة"));
function applyTheme(theme){const light=theme==="light";document.body.classList.toggle("light-mode",light);$$("[data-theme]").forEach(x=>x.classList.toggle("active",x.dataset.theme===theme));}
function loadSettings(){try{return JSON.parse(localStorage.getItem(SETTINGS_KEY)||"{}")}catch{return {}}}
const savedSettings=loadSettings();applyTheme(savedSettings.theme||"dark");
if(savedSettings.accent){document.documentElement.style.setProperty("--blue",savedSettings.accent);if($("#accentColor"))$("#accentColor").value=savedSettings.accent;}
$("#themeToggle").addEventListener("click",()=>{const theme=document.body.classList.contains("light-mode")?"dark":"light";applyTheme(theme);localStorage.setItem(SETTINGS_KEY,JSON.stringify({...loadSettings(),theme}));toast(theme==="light"?"تم تفعيل المظهر الفاتح":"تم تفعيل المظهر الداكن")});
$$("[data-theme]").forEach(b=>b.addEventListener("click",()=>{applyTheme(b.dataset.theme);localStorage.setItem(SETTINGS_KEY,JSON.stringify({...loadSettings(),theme:b.dataset.theme}));}));
$("#accentColor")?.addEventListener("input",e=>{document.documentElement.style.setProperty("--blue",e.target.value);localStorage.setItem(SETTINGS_KEY,JSON.stringify({...loadSettings(),accent:e.target.value}))});
$("#saveSettings")?.addEventListener("click",()=>{
  const settings={...loadSettings(),theme:document.body.classList.contains("light-mode")?"light":"dark",accent:$("#accentColor")?.value||"#0789f9",language:$("#language")?.value||"العربية",reminders:$$('.setting-card input[type="checkbox"]').map(x=>x.checked),studyDuration:$$('.setting-card select')[1]?.value||"45 دقيقة",breakDuration:$$('.setting-card select')[2]?.value||"5 دقائق"};
  localStorage.setItem(SETTINGS_KEY,JSON.stringify(settings));$("#settingsStatus").textContent="حُفظت الإعدادات على هذا المتصفح.";toast("تم حفظ الإعدادات");
});
$("#editProfile").addEventListener("click",()=>{
  const user=getAccount(); if(!user){toast("سجّل الدخول أولاً");return}
  const name=prompt("اكتب الاسم الذي تريد عرضه:",user.name);
  if(name===null)return;
  if(!name.trim()){toast("الاسم لا يمكن أن يكون فارغًا");return}
  const levels=["middle","secondary","university","master","other"];
  const currentLevel=levels.includes(user.level)?user.level:"university";
  const levelInput=prompt("اختر المستوى بكتابة الرقم:\n1- متوسط\n2- ثانوي\n3- جامعة (ليسانس)\n4- ماستر\n5- آخر",String(levels.indexOf(currentLevel)+1));
  if(levelInput===null)return;
  const chosen=levels[Number(levelInput)-1];if(!chosen){toast("اختيار المستوى غير صحيح");return}
  const options=yearOptions(chosen);const yearInput=prompt("اختر السنة بكتابة الرقم:\n"+options.map((o,i)=>`${i+1}- ${o.label}`).join("\n"),String(Math.max(1,options.findIndex(o=>o.value===String(user.year))+1)));
  if(yearInput===null)return;const yearOption=options[Number(yearInput)-1];if(!yearOption){toast("اختيار السنة غير صحيح");return}
  user.name=name.trim();user.level=chosen;user.year=yearOption.value;localStorage.setItem(AUTH_KEY,JSON.stringify(user));applyUser(user);toast("تم تحديث الاسم والمستوى الدراسي");
});
$("#contactBtn")?.addEventListener("click",()=>toast("واجهة الدعم جاهزة للتوصيل بخدمة Backend"));
$("#attachBtn").addEventListener("click",()=>{
  const picker=document.createElement("input");picker.type="file";picker.accept=".pdf,.txt,.md,.doc,.docx,.png,.jpg,.jpeg";
  picker.addEventListener("change",()=>{const file=picker.files?.[0];if(!file)return;const input=$("#chatInput");input.value=(input.value?input.value+" ":"")+`[ملف مرفق: ${file.name}]`;input.focus();toast(`تم اختيار ${file.name}. قراءة محتوى الملف تتطلب ربط Backend.`)});picker.click();
});
$("#globalSearch").addEventListener("keydown",e=>{
  if(e.key==="Enter"){
    const raw=e.target.value.trim(),q=raw.toLowerCase();if(!q)return;
    const match=[["مساعد","assistant"],["اختبار","exams"],["جدول","schedule"],["تنظيم","schedule"],["مكتبة","library"],["ملف","library"],["تركيز","focus"],["مؤقت","focus"],["إعداد","settings"],["مساعدة","help"],["حساب","account"],["دراسة","home"]].find(([word])=>q.includes(word));
    showPage(match?match[1]:"assistant");
    if(!match){$("#chatInput").value=raw;$("#chatInput").focus()}else toast("تم فتح القسم المناسب للبحث");
  }
});
const activityData={
 weekly:[["السبت","2 س","72","code"],["الأحد","1.5 س","46","book-open"],["الإثنين","30 د","13","flask-conical"],["الثلاثاء","45 د","20","file-text"],["الأربعاء","10 د","4","brain"],["الخميس","1.8 س","53","chart-no-axes-combined"],["الجمعة","2 س","61","calendar-days"]],
 monthly:[["الأسبوع 1","7 س","70","book-open"],["الأسبوع 2","5 س","50","code"],["الأسبوع 3","8 س","82","brain"],["الأسبوع 4","6 س","61","calendar-days"]]
};
function renderActivity(range="weekly"){
  $("#activityList").innerHTML=activityData[range].map(([day,time,width,icon])=>`<div class="activity-row"><span class="activity-icon"><i data-lucide="${icon}"></i></span><span class="activity-day">${day}</span><div class="activity-track"><span style="width:${width}%"></span></div><span class="activity-time">${time}</span></div>`).join("");
  window.lucide?.createIcons();
}
$$("[data-range]").forEach(b=>b.addEventListener("click",()=>{$$("[data-range]").forEach(x=>x.classList.toggle("active",x===b));renderActivity(b.dataset.range)}));

// User-editable weekly timetable, persisted in this browser.
const DEFAULT_EVENTS=[
  ["الاثنين","رياضيات","08:00","10:00","blue"],["الاثنين","برمجة","10:15","12:15","purple"],["الاثنين","قواعد البيانات","14:00","16:00","green"],
  ["الثلاثاء","خوارزميات","08:00","10:00","green"],["الثلاثاء","منطق رياضي","10:15","12:15","purple"],
  ["الأربعاء","رياضيات","08:00","10:00","blue"],["الأربعاء","قواعد البيانات","14:00","16:00","green"],
  ["الخميس","خوارزميات","08:00","10:00","green"],["الخميس","أنظمة التشغيل","18:00","19:30","green"],
  ["الجمعة","برمجة","10:15","12:15","purple"],["السبت","مراجعة عامة","10:00","12:00","blue"]
];
const SCHEDULE_KEY="talaba_user_schedule_v1";
function loadEvents(){try{const saved=JSON.parse(localStorage.getItem(SCHEDULE_KEY)||"null");return Array.isArray(saved)?saved:DEFAULT_EVENTS.map(e=>({day:e[0],subject:e[1],start:e[2],end:e[3],color:e[4]}))}catch{return DEFAULT_EVENTS.map(e=>({day:e[0],subject:e[1],start:e[2],end:e[3],color:e[4]}))}}
let events=loadEvents();
function saveEvents(){localStorage.setItem(SCHEDULE_KEY,JSON.stringify(events))}
function renderSchedule(){
  const days=["الاثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت","الأحد"];
  let html='<div class="day-head">الوقت</div>'+days.map(d=>`<div class="day-head">${d}</div>`).join("");
  const times=["08:00","10:00","12:00","14:00","16:00","18:00","20:00"];
  times.forEach((time,idx)=>{
    html+=`<div class="time-head">${time}</div>`;
    days.forEach(day=>{
      const ev=events.find(e=>e.day===day&&((idx===0&&e.start<="08:59"&&e.end>"08:00")||(idx===1&&e.start<="10:59"&&e.end>"10:00")||(idx===2&&e.start<="12:59"&&e.end>"12:00")||(idx===3&&e.start<="14:59"&&e.end>"14:00")||(idx===4&&e.start<="16:59"&&e.end>"16:00")||(idx===5&&e.start<="18:59"&&e.end>"18:00")||(idx===6&&e.start<="20:59"&&e.end>"20:00")));
      html+=`<div class="slot">${ev?`<span class="event ${ev.color}">${escapeHtml(ev.subject)}<br>${ev.start} - ${ev.end}</span>`:""}</div>`;
    });
  });
  $("#scheduleGrid").innerHTML=html;
  renderScheduleEntries();
}
function escapeHtml(value){return String(value).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function renderScheduleEntries(){
  const list=$("#scheduleEntries");if(!list)return;
  if(!events.length){list.innerHTML='<div class="schedule-empty">لم تضف أي حصة بعد. استخدم النموذج أعلاه لإدخال جدولك.</div>';return}
  list.innerHTML=events.map((e,i)=>`<div class="schedule-entry"><span class="entry-dot" style="background:${e.color==="purple"?"#8a52ff":e.color==="green"?"#00d49a":"#0789f9"}"></span><span class="entry-text"><b>${escapeHtml(e.subject)}</b> <small>— ${e.day}، ${e.start} إلى ${e.end}</small></span><button type="button" data-delete-event="${i}" aria-label="حذف ${escapeHtml(e.subject)}">حذف</button></div>`).join("");
  $$("[data-delete-event]").forEach(btn=>btn.addEventListener("click",()=>{events.splice(Number(btn.dataset.deleteEvent),1);saveEvents();renderSchedule();toast("تم حذف الحصة من جدولك")}));
}
$("#scheduleForm").addEventListener("submit",e=>{
  e.preventDefault();
  const subject=$("#subjectInput").value.trim(),day=$("#dayInput").value,start=$("#startInput").value,end=$("#endInput").value,color=$("#colorInput").value;
  if(!subject){toast("اكتب اسم المادة");return}
  if(start>=end){toast("وقت النهاية يجب أن يكون بعد وقت البداية");return}
  const conflict=events.find(x=>x.day===day&&start<x.end&&end>x.start);
  if(conflict&&!confirm(`يوجد تداخل مع ${conflict.subject} (${conflict.start}–${conflict.end}). هل تريد إضافة الحصة رغم ذلك؟`))return;
  events.push({day,subject,start,end,color});saveEvents();renderSchedule();e.target.reset();$("#startInput").value="08:00";$("#endInput").value="10:00";toast("تمت إضافة الحصة إلى جدولك");
});
const tasksKey="talaba_tasks_v1";
let tasks;
try{tasks=JSON.parse(localStorage.getItem(tasksKey)||"null")||[{text:"حل التمرين 2 - الخوارزميات",date:"07 أكتوبر",tag:"برمجة",done:false},{text:"مراجعة الفصل 3",date:"08 أكتوبر",tag:"خوارزميات",done:false},{text:"قراءة الفصل 4",date:"10 أكتوبر",tag:"قواعد البيانات",done:false}]}catch{tasks=[]}
function saveTasks(){localStorage.setItem(tasksKey,JSON.stringify(tasks))}
function renderTasks(){
  $("#tasks").innerHTML=tasks.map((t,i)=>`<label class="task-row ${t.done?"done":""}"><input type="checkbox" data-task="${i}" ${t.done?"checked":""}><span>${escapeHtml(t.text)}</span><small class="task-date">${escapeHtml(t.date)}</small></label>`).join("");
  $("#taskCount").textContent=tasks.filter(t=>!t.done).length;
  $$("[data-task]").forEach(c=>c.addEventListener("change",e=>{tasks[+e.target.dataset.task].done=e.target.checked;saveTasks();renderTasks();refreshDashboard()}));
}
$("#addTask").addEventListener("click",()=>{
  const text=prompt("ما المهمة التي تريد إضافتها؟");if(text&&text.trim()){tasks.push({text:text.trim(),date:"قريباً",tag:"عام",done:false});saveTasks();renderTasks();refreshDashboard();toast("تمت إضافة المهمة")}
});
const exams=[
 {name:"اختبار الخوارزميات",desc:"أسئلة حول أساسيات الخوارزميات وبنية البرامج",meta:"40 سؤالاً • 45 دقيقة",status:"done",score:"8.5 / 10",icon:"clipboard-list"},
 {name:"اختبار هياكل البيانات",desc:"أسئلة حول المصفوفات، القوائم والأشجار",meta:"12 سؤالاً • 60 دقيقة",status:"todo",score:"— / 10",icon:"database"},
 {name:"اختبار المنطق البرمجي",desc:"أسئلة حول العبارات الشرطية والحلقات",meta:"8 أسئلة • 40 دقيقة",status:"done",score:"9 / 10",icon:"code"},
 {name:"اختبار الأساسيات",desc:"مراجعة عامة للدروس الأولى",meta:"45 سؤالاً • 70 دقيقة",status:"todo",score:"— / 10",icon:"book-open"},
 {name:"اختبار قواعد البيانات",desc:"أسئلة حول قواعد البيانات و SQL",meta:"40 سؤالاً • 50 دقيقة",status:"todo",score:"— / 10",icon:"network"}
];
function renderExams(filter="all"){
  $("#examList").innerHTML=exams.filter(e=>filter==="all"||(filter==="done"?e.status==="done":e.status==="todo")).map((e,i)=>`<article class="exam-row ${e.status}"><span class="exam-icon"><i data-lucide="${e.icon}"></i></span><div><h3>${e.name}</h3><p>${e.desc}</p><p>${e.meta}</p></div><span class="exam-status">${e.status==="done"?"● مكتمل":"◷ قيد الإنجاز"}</span><div class="exam-score">${e.score}<small>النتيجة</small></div><button class="outline-btn exam-action" data-exam="${e.name}" data-status="${e.status}">${e.status==="done"?"مراجعة":"بدء الاختبار"}　›</button></article>`).join("");
  window.lucide?.createIcons();
  // The quiz handler is attached once by the feature layer below; avoid duplicate clicks.
}
$$("[data-filter]").forEach(b=>b.addEventListener("click",()=>{$$("[data-filter]").forEach(x=>x.classList.toggle("active",x===b));renderExams(b.dataset.filter)}));
function sendMessage(text){
  if(!text.trim())return;
  const area=$("#chatMessages");
  if(area.classList.contains("chat-empty")){area.classList.remove("chat-empty");area.innerHTML="";area.style.display="flex";area.style.flexDirection="column";area.style.alignItems="stretch";area.style.justifyContent="flex-start"}
  const user=document.createElement("div");user.className="message user";user.textContent=text;area.appendChild(user);
  const answer=document.createElement("div");answer.className="message bot";answer.textContent="وصل سؤالك! هذه واجهة أولية للمساعد. للحصول على إجابات ذكية فعلية، يلزم ربطها بواجهة API آمنة في الـ Backend.";area.appendChild(answer);
  $("#chatInput").value="";area.scrollTop=area.scrollHeight;
}
$("#chatForm").addEventListener("submit",e=>{e.preventDefault();sendMessage($("#chatInput").value)});
$$("[data-prompt]").forEach(b=>b.addEventListener("click",()=>{showPage("assistant");sendMessage(b.dataset.prompt)}));
renderActivity();renderSchedule();renderTasks();renderExams();renderLibrary();renderFocusHistory();paintTimer();refreshDashboard();window.lucide?.createIcons();


// Real dashboard metrics from completed tasks, focus sessions and quiz attempts.
function readStore(key,fallback=[]){try{const v=JSON.parse(localStorage.getItem(key)||"null");return Array.isArray(v)?v:fallback}catch{return fallback}}
function escapeText(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function formatMinutes(total){total=Math.max(0,Math.round(total));const h=Math.floor(total/60),m=total%60;return h?`${h} س ${m} د`:`${m} دقيقة`}
function refreshDashboard(){
  const done=tasks.filter(t=>t.done).length, completion=tasks.length?Math.round(done/tasks.length*100):0;
  const sessions=readStore(FOCUS_KEY), total=sessions.reduce((s,x)=>s+(Number(x.minutes)||0),0);
  const quizResults=readStore(QUIZ_KEY), avg=quizResults.length?quizResults.reduce((s,x)=>s+x.score,0)/quizResults.length:null;
  const weak=Math.max(0,quizResults.reduce((s,x)=>s+(x.total-x.correct),0));
  const set=(id,value)=>{const el=$("#"+id);if(el)el.textContent=value};
  set("dashCompletion",completion+"%");
  set("dashExamScore",avg===null?"— / 20":(avg*2).toFixed(1)+" / 20");
  set("dashStudyTime",formatMinutes(total));
  set("dashWeakTopics",weak);
  const bar=(id,val)=>{const el=$("#"+id);if(el)el.style.width=Math.max(0,Math.min(100,val))+"%"};
  bar("dashCompletionBar",completion);bar("dashExamBar",avg===null?0:avg*10);bar("dashStudyBar",Math.min(100,total/300*100));bar("dashWeakBar",Math.min(100,weak*10));
  const today=$("#todayLabel");if(today)today.textContent=new Intl.DateTimeFormat("ar-DZ",{weekday:"long",day:"numeric",month:"long"}).format(new Date());
  const next=$("#nextStepText");
  if(next){const pending=tasks.find(t=>!t.done);next.textContent=pending?`ابدأ الآن: ${pending.text}. خصص جلسة قصيرة وأنهِ خطوة واحدة.`:"أحسنت! لا توجد مهام مفتوحة. أضف مهمة جديدة أو راجع درسًا تحتاج إلى تثبيته."}
}

// Focus timer with pause/resume, selectable durations, and local session history.
let focusMinutes=25, remainingSeconds=1500, timerInterval=null, timerRunning=false;
function paintTimer(){
  const display=$("#timerDisplay"),status=$("#timerStatus"),ring=$("#timerRing");
  if(display)display.textContent=`${String(Math.floor(remainingSeconds/60)).padStart(2,"0")}:${String(remainingSeconds%60).padStart(2,"0")}`;
  if(status)status.textContent=timerRunning?"جلسة تركيز جارية":remainingSeconds===focusMinutes*60?"جاهز للبدء":remainingSeconds===0?"اكتملت الجلسة":"متوقف مؤقتًا";
  if(ring){const progress=1-remainingSeconds/(focusMinutes*60||1);ring.style.background=`conic-gradient(#0789f9 ${progress*360}deg,#123b60 ${progress*360}deg)`;}
  const btn=$("#timerStart");if(btn)btn.innerHTML=timerRunning?'<i data-lucide="pause"></i> إيقاف مؤقت':'<i data-lucide="play"></i> '+(remainingSeconds<focusMinutes*60&&remainingSeconds>0?'متابعة':'ابدأ');
  window.lucide?.createIcons();
}
function renderFocusHistory(){
  const host=$("#focusHistory");if(!host)return;
  const items=readStore(FOCUS_KEY).slice(-8).reverse();
  host.innerHTML=items.length?items.map(x=>`<div class="focus-history-row"><i data-lucide="check-circle-2"></i><div><b>${escapeText(x.task||"جلسة دراسة")}</b><small>${x.minutes} دقيقة • ${escapeText(x.date||"")}</small></div></div>`).join(""):'<div class="library-empty">لم تُسجّل جلسات بعد. ابدأ أول جلسة تركيز!</div>';
  window.lucide?.createIcons();
}
function completeFocusSession(){
  clearInterval(timerInterval);timerInterval=null;timerRunning=false;remainingSeconds=0;paintTimer();
  const task=$("#focusTask")?.value.trim()||"جلسة دراسة";
  const items=readStore(FOCUS_KEY);items.push({task,minutes:focusMinutes,date:new Date().toLocaleString("ar-DZ")});
  localStorage.setItem(FOCUS_KEY,JSON.stringify(items));renderFocusHistory();refreshDashboard();toast("أحسنت! اكتملت جلسة التركيز وسُجّل وقتها");
}
$("#timerStart")?.addEventListener("click",()=>{
  if(timerRunning){clearInterval(timerInterval);timerInterval=null;timerRunning=false;paintTimer();return}
  if(remainingSeconds<=0){remainingSeconds=focusMinutes*60}
  timerRunning=true;paintTimer();
  timerInterval=setInterval(()=>{remainingSeconds--;paintTimer();if(remainingSeconds<=0)completeFocusSession()},1000);
});
$("#timerReset")?.addEventListener("click",()=>{clearInterval(timerInterval);timerInterval=null;timerRunning=false;remainingSeconds=focusMinutes*60;paintTimer();toast("تمت إعادة ضبط المؤقت")});
$$("[data-minutes]")?.forEach(b=>b.addEventListener("click",()=>{
  clearInterval(timerInterval);timerInterval=null;timerRunning=false;focusMinutes=Number(b.dataset.minutes);remainingSeconds=focusMinutes*60;
  $$("[data-minutes]").forEach(x=>x.classList.toggle("active",x===b));paintTimer();
}));
$("#startRecommended")?.addEventListener("click",()=>{showPage("focus");if($("#tasks")){const p=tasks.find(t=>!t.done);if(p)$("#focusTask").value=p.text}});

// Local library: note metadata and selected files are stored in browser storage.
function renderLibrary(){
  const host=$("#libraryList");if(!host)return;
  const q=($("#librarySearch")?.value||"").trim().toLowerCase();
  const items=readStore(LIBRARY_KEY).filter(x=>!q||`${x.title} ${x.subject} ${x.content||""}`.toLowerCase().includes(q));
  host.innerHTML=items.length?items.map((x,i)=>`<div class="library-item"><div class="library-item-icon"><i data-lucide="${x.type==="file"?"file-text":"notebook-pen"}"></i></div><div class="library-item-main"><b>${escapeText(x.title)}</b><small>${escapeText(x.subject)} • ${x.type==="file"?"ملف":"ملاحظة"} • ${escapeText(x.date||"")}</small>${x.content?`<p>${escapeText(x.content).slice(0,260)}${x.content.length>260?"…":""}</p>`:""}${x.fileName?`<small>الملف: ${escapeText(x.fileName)} (${formatBytes(x.fileSize||0)})</small>`:""}</div><div class="library-item-actions"><button data-library-open="${x.id}">عرض</button><button data-library-delete="${x.id}">حذف</button></div></div>`).join(""):'<div class="library-empty">المكتبة فارغة. أضف أول ملف أو ملاحظة من النموذج أعلاه.</div>';
  $$("[data-library-delete]").forEach(b=>b.addEventListener("click",()=>{const arr=readStore(LIBRARY_KEY).filter(x=>x.id!==b.dataset.libraryDelete);localStorage.setItem(LIBRARY_KEY,JSON.stringify(arr));renderLibrary();toast("تم حذف العنصر")}));
  $$("[data-library-open]").forEach(b=>b.addEventListener("click",()=>{const item=readStore(LIBRARY_KEY).find(x=>x.id===b.dataset.libraryOpen);if(!item)return;if(item.content)alert(`${item.title}\\n\\n${item.content}`);else toast(item.fileName?`اسم الملف: ${item.fileName}. احتفظ بالملف الأصلي على جهازك.`:"لا يوجد محتوى للعرض")}));
  window.lucide?.createIcons();
}
function formatBytes(n){if(n<1024)return n+" B";if(n<1048576)return (n/1024).toFixed(1)+" KB";return (n/1048576).toFixed(1)+" MB"}
$("#libraryType")?.addEventListener("change",()=>{
  const isFile=$("#libraryType").value==="file";
  $("#libraryFile").closest("label").classList.toggle("hidden",!isFile);
  $("#libraryContent").closest("label").classList.toggle("hidden",isFile);
});
$("#libraryForm")?.addEventListener("submit",async e=>{
  e.preventDefault();
  const type=$("#libraryType").value,file=$("#libraryFile").files[0],title=$("#libraryTitle").value.trim(),subject=$("#librarySubject").value.trim(),content=$("#libraryContent").value.trim();
  if(type==="file"&&!file){toast("اختر ملفًا أولًا");return}
  if(type==="note"&&!content){toast("اكتب محتوى الملاحظة");return}
  // Store metadata, not file bytes, to avoid filling localStorage with large files.
  const items=readStore(LIBRARY_KEY);items.push({id:crypto.randomUUID?crypto.randomUUID():String(Date.now()),title,subject,type,content:type==="note"?content:"",fileName:file?.name||"",fileSize:file?.size||0,date:new Date().toLocaleDateString("ar-DZ")});
  try{localStorage.setItem(LIBRARY_KEY,JSON.stringify(items))}catch{toast("مساحة التخزين ممتلئة؛ احذف بعض العناصر وحاول مجددًا");return}
  e.target.reset();$("#libraryType").dispatchEvent(new Event("change"));renderLibrary();toast(type==="file"?"تم حفظ بيانات الملف. احتفظ بنسخته الأصلية على جهازك.":"تم حفظ الملاحظة في المكتبة");
});
$("#librarySearch")?.addEventListener("input",renderLibrary);

// Practice quiz with explanations; score persists for dashboard.
const quizBank=[
 {q:"ما الغرض الأساسي من الخوارزمية؟",options:["تزيين واجهة البرنامج","تحديد خطوات واضحة لحل مشكلة","تخزين الصور فقط","استبدال نظام التشغيل"],answer:1,explain:"الخوارزمية سلسلة خطوات واضحة ومنطقية لحل مشكلة."},
 {q:"ما نوع المتغير الأنسب لتخزين قيمة مثل 12.5؟",options:["Entier / Integer","Booléen / Boolean","Réel / Real","Caractère / Character"],answer:2,explain:"النوع Réel (Real) يسمح بتخزين الأعداد ذات الجزء العشري."},
 {q:"ماذا يفعل الشرط Si...Sinon (if...else)؟",options:["يكرر الأوامر دائمًا","يختار مسارًا وفق شرط","يحذف المتغيرات","يطبع كل القيم تلقائيًا"],answer:1,explain:"الشرط يحدد أي مجموعة أوامر تنفذ وفق تحقق الشرط."},
 {q:"لماذا نهيّئ المجموع إلى صفر قبل التجميع؟",options:["لأن الصفر أكبر عدد","حتى يبدأ المجموع من قيمة معروفة","لأن المتغير لا يحتاج قيمة","لتجنب إدخال البيانات"],answer:1,explain:"نبدأ من صفر كي لا تؤثر قيمة قديمة أو غير معروفة في عملية الجمع."},
 {q:"أي تعليمة تقرأ قيمة من المستخدم في الخوارزمية؟",options:["Afficher","Lire","Fin","Si"],answer:1,explain:"Lire تعني قراءة مدخلات المستخدم."}
];
let quizState={active:false,index:0,correct:0,selected:null,answered:false,examName:"اختبار تدريبي"};
function startQuiz(name){
  quizState={active:true,index:0,correct:0,selected:null,answered:false,examName:name||"اختبار تدريبي"};
  $("#quizTitle").textContent=quizState.examName;$("#quizModal").classList.remove("hidden");renderQuizQuestion();
}
function renderQuizQuestion(){
  const item=quizBank[quizState.index];$("#quizProgress").textContent=`السؤال ${quizState.index+1} من ${quizBank.length} • الإجابات الصحيحة: ${quizState.correct}`;
  $("#quizBody").innerHTML=`<div class="quiz-question">${escapeText(item.q)}</div><div class="quiz-options">${item.options.map((o,i)=>`<label class="quiz-option"><input type="radio" name="quizAnswer" value="${i}"><span>${escapeText(o)}</span></label>`).join("")}</div>`;
  $("#quizFeedback").textContent="";$("#quizFeedback").className="quiz-feedback";$("#submitAnswer").classList.remove("hidden");$("#nextQuestion").classList.add("hidden");quizState.selected=null;quizState.answered=false;
}
$("#submitAnswer")?.addEventListener("click",()=>{
  if(quizState.answered)return;
  const selected=$('input[name="quizAnswer"]:checked',$("#quizBody"));
  if(!selected){toast("اختر إجابة أولًا");return}
  quizState.selected=Number(selected.value);quizState.answered=true;
  const item=quizBank[quizState.index],correct=quizState.selected===item.answer;
  if(correct)quizState.correct++;
  $("#quizFeedback").textContent=(correct?"إجابة صحيحة! ":"ليست الإجابة الصحيحة. ")+item.explain;
  $("#quizFeedback").classList.add(correct?"correct":"wrong");
  $$('input[name="quizAnswer"]',$("#quizBody")).forEach(x=>x.disabled=true);
  $("#submitAnswer").classList.add("hidden");$("#nextQuestion").classList.remove("hidden");
});
$("#nextQuestion")?.addEventListener("click",()=>{
  if(quizState.index<quizBank.length-1){quizState.index++;renderQuizQuestion();return}
  const results=readStore(QUIZ_KEY);results.push({name:quizState.examName,correct:quizState.correct,total:quizBank.length,score:quizState.correct/quizBank.length*10,date:new Date().toLocaleDateString("ar-DZ")});
  localStorage.setItem(QUIZ_KEY,JSON.stringify(results));
  $("#quizBody").innerHTML=`<div class="quiz-question">أكملت الاختبار!</div><p>نتيجتك: <b>${quizState.correct} من ${quizBank.length}</b> (${Math.round(quizState.correct/quizBank.length*100)}%)</p><p class="muted">راجع الإجابات الخاطئة ثم أعد المحاولة لاحقًا.</p>`;
  $("#quizProgress").textContent="النتيجة النهائية";$("#quizFeedback").textContent="تم حفظ نتيجتك في هذا المتصفح.";$("#submitAnswer").classList.add("hidden");$("#nextQuestion").textContent="إغلاق";$("#nextQuestion").onclick=()=>{closeQuiz();renderExams();refreshDashboard();};$("#nextQuestion").classList.remove("hidden");
});
function closeQuiz(){ $("#quizModal").classList.add("hidden");$("#nextQuestion").textContent="السؤال التالي";$("#nextQuestion").onclick=null; }
$("#closeQuiz")?.addEventListener("click",closeQuiz);$("#cancelQuiz")?.addEventListener("click",closeQuiz);

// Replace placeholder exam buttons with a real practice quiz for unfinished exams.
const originalRenderExams=renderExams;
renderExams=function(filter="all"){
  originalRenderExams(filter);
  $$(".exam-action").forEach(b=>{
    b.onclick=()=>{if(b.dataset.status==="done"){toast("الاختبارات المكتملة محفوظة كبيانات تجريبية؛ يمكنك بدء اختبار تدريبي جديد.");startQuiz(b.dataset.exam)}else startQuiz(b.dataset.exam)};
  });
};

document.addEventListener("keydown",e=>{if(e.key==="Escape"&&$("#quizModal")&&!$("#quizModal").classList.contains("hidden"))closeQuiz()});
