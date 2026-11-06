import {createApp, markRaw} from '/cat-vendor/vue.mjs';
import {readPage, acceptMessage, sendOutcome, errorText, seatLabels} from './cat-state.mjs';

const dayFormat = new Intl.DateTimeFormat('zh-CN', {month:'long',day:'numeric',weekday:'short'});
const timeFormat = new Intl.DateTimeFormat('zh-CN', {hour:'2-digit',minute:'2-digit',hour12:false});
const themes = ['light','dark','corporate','retro'];
const endpoint = (id, suffix='') => '/api/room/' + encodeURIComponent(id) + suffix;
function newConversation(id) {
  return {id,title:'',status:'open',members:[],messages:[],cursor:0,draft:'',reply:'',pending:null,
          feedback:'发言按真实身份保存。',outcome:'',loaded:false};
}
async function request(path, options={}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.method==='POST' ? 20000 : 15000);
  try {
    const response = await fetch(path, {...options,signal:controller.signal,cache:'no-store'});
    const value = await response.json();
    if (!response.ok && value.status===undefined) value.status=response.status;
    return value;
  } finally { clearTimeout(timeout); }
}
function checked(value) { if (!value.ok) throw new Error(errorText(value)); return value; }

createApp({
  data() {
    const savedTheme=localStorage.getItem('cat.theme');
    return {rooms:[],people:[],roomStates:{},roomId:'',filter:'',roomScope:'open',sidebar:false,
      theme:themes.includes(savedTheme)?savedTheme:'light',seatLabels,selection:0,stream:null,
      connection:'正在连接',connectionError:false,unseen:0,highlight:'',checking:false,
      createTitle:'',createMembers:[],createError:'',createdRoomId:'',creating:false,createUnknown:false};
  },
  computed: {
    state() { return this.roomStates[this.roomId] || null; },
    reply() { return this.state?.messages.find(message=>message.id===this.state.reply); },
    filteredRooms() {
      return this.rooms.filter(room=>room.status===this.roomScope && (room.title||'').toLowerCase().includes(this.filter.trim().toLowerCase()))
        .slice().sort((a,b)=>b.created_at.localeCompare(a.created_at));
    },
    canCompose() {
      const human=this.state?.members.find(member=>member.home_id==='human');
      return !!this.state?.loaded && this.state.status==='open' && !this.state.pending &&
        (!human || human.state==='participant');
    },
    canSend() { return this.canCompose && !!this.state.draft.trim(); },
    placeholder() {
      if (!this.state) return '选择房间后开始发言…';
      if (this.state.status==='closed') return '讨论已结束，可以继续阅读。';
      const human=this.state.members.find(member=>member.home_id==='human');
      if (human && human.state!=='participant') return '你当前为'+(seatLabels[human.state]||human.state)+'，发言已暂停。';
      return '写下想法，或回复一条消息…';
    },
  },
  watch: {
    theme(value) { document.documentElement.dataset.theme=value; localStorage.setItem('cat.theme',value); },
  },
  methods: {
    day(value) { return dayFormat.format(new Date(value)); },
    time(value) { return timeFormat.format(new Date(value)); },
    name(id) {
      if (id==='human') return 'Human';
      const member=this.state?.members.find(item=>item.home_id===id);
      if (member?.label && member.label!==id) return member.label;
      return this.people.find(person=>person.id===id)?.name || member?.label || id;
    },
    avatar(id) {
      if (id==='human') return '你';
      const number=this.people.find(person=>person.id===id)?.number;
      return number || this.name(id).slice(0,2);
    },
    quote(id) {
      const message=this.state?.messages.find(item=>item.id===id);
      return message ? this.name(message.sender_id)+'：'+message.body.replace(/\n/g,' ') : '回复较早的消息';
    },
    textParts(body) {
      const parts=[],pattern=/https?:\/\/[^\s<>()，。；]+/g; let end=0;
      for (const match of body.matchAll(pattern)) {
        parts.push({text:body.slice(end,match.index)},{text:match[0],url:match[0]});
        end=match.index+match[0].length;
      }
      parts.push({text:body.slice(end)});
      return parts;
    },
    setDraft(value) { if (this.state) this.state.draft=value; },
    closeSidebarFromContent() { this.sidebar=false; },
    nearEnd() { const el=this.$refs.messages; return el.scrollHeight-el.scrollTop-el.clientHeight<100; },
    scrollBottom() { const el=this.$refs.messages; el.scrollTop=el.scrollHeight; this.unseen=0; },
    onScroll() { if (this.nearEnd()) this.unseen=0; },
    replyTo(id) { if (this.canCompose) {this.state.reply=id;this.$nextTick(()=>this.$refs.input.focus());} },
    cancelReply() { if (this.state) this.state.reply=''; this.$nextTick(()=>this.$refs.input.focus()); },
    jumpTo(id) {
      const target=[...this.$refs.messages.querySelectorAll('[data-message-id]')].find(node=>node.dataset.messageId===id);
      if (target) {target.scrollIntoView({block:'center'});this.highlight=id;setTimeout(()=>{if(this.highlight===id)this.highlight='';},1800);}
    },
    confirmPending(state) {
      // A stream event may precede the POST receipt. Keep the composer owned
      // by that request until it settles, so its receipt cannot clear a new draft.
      if (!state.pending || state.pending.sending || !state.messages.some(message=>message.id===state.pending.id)) return;
      state.pending=null;state.draft='';state.reply='';state.outcome='saved';
      state.feedback='已核到原消息 · 消息已保存，提醒结果以原回执为准。';
    },
    async loadRooms() {
      this.rooms=checked(await request('/api/cat/rooms')).rooms;
      return this.rooms;
    },
    async loadPeople() { this.people=checked(await request('/api/cat/people')).people; },
    async selectRoom(id) {
      this.sidebar=false;
      if (this.roomId===id && this.state?.loaded) return;
      this.stopStream(); const generation=++this.selection;
      if (!this.roomStates[id]) this.roomStates[id]=newConversation(id);
      this.roomId=id;const state=this.state,summary=this.rooms.find(room=>room.id===id);
      if (summary) {state.title=summary.title;state.status=summary.status;this.roomScope=summary.status;}
      const url=new URL(location.href);url.searchParams.set('room',id);history.replaceState(null,'',url);
      this.connection='正在读取';this.connectionError=false;this.unseen=0;
      try {
        const room=checked(await request(endpoint(id)));
        Object.assign(state,{title:room.title,status:room.status,members:room.members,loaded:true},readPage(state,room.messages));
        this.confirmPending(state);
        if (generation!==this.selection) return;
        this.roomScope=room.status;document.title=(room.title||'圆桌')+' · CAT';
        await this.$nextTick();this.scrollBottom();this.startStream(state);
      } catch(error) {
        if(generation!==this.selection)return;
        this.connection='读取失败';this.connectionError=true;state.feedback=error.message;state.outcome='failed';
      }
    },
    stopStream() { if(this.stream){this.stream.close();this.stream=null;} },
    startStream(state) {
      this.stopStream();
      if(document.hidden || this.roomId!==state.id)return;
      const stream=markRaw(new EventSource(endpoint(state.id,'/events?after='+state.cursor)));
      this.stream=stream;const generation=this.selection;
      this.connection='正在接入实时消息';this.connectionError=false;
      stream.addEventListener('room',async event=>{
        if(this.stream!==stream || generation!==this.selection)return;
        const update=JSON.parse(event.data),near=this.nearEnd(),count=state.messages.length;
        Object.assign(state,readPage(state,update.messages),{title:update.title,status:update.status,members:update.members});
        this.confirmPending(state);
        const summary=this.rooms.find(room=>room.id===state.id);
        if(summary){summary.title=state.title;summary.status=state.status;summary.message_count=state.messages.length;summary.member_count=state.members.length;}
        this.connection='实时连接';this.connectionError=false;
        await this.$nextTick();
        if(this.roomId!==state.id)return;
        if(near)this.scrollBottom();else this.unseen+=Math.max(0,state.messages.length-count);
      });
      stream.onerror=()=>{
        if(this.stream!==stream)return;
        this.connection='实时连接中断 · 正在重连';this.connectionError=true;
      };
    },
    async refresh() {
      try {
        await Promise.all([this.loadRooms(),this.loadPeople()]);
        if(this.state) {
          const state=this.state,room=checked(await request(endpoint(state.id)));
          Object.assign(state,{title:room.title,status:room.status,members:room.members,loaded:true},readPage(state,room.messages));
          this.confirmPending(state);this.startStream(state);
        }
      } catch(error) {this.connection=error.message;this.connectionError=true;}
    },
    onComposerKey(event) {
      if(!event.isComposing && (event.ctrlKey||event.metaKey) && event.key==='Enter'){event.preventDefault();this.send();}
    },
    async send() {
      if(!this.canSend)return;
      const state=this.state,outgoing={id:'human-'+crypto.randomUUID(),body:state.draft.trim(),reply:state.reply,sending:true};
      state.pending=outgoing;state.feedback='正在保存消息…';state.outcome='';
      let value;
      try {value=await request(endpoint(state.id,'/message'),{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message_id:outgoing.id,body:outgoing.body,reply_to:outgoing.reply})});}
      catch(error){value={ok:false,error:error.message};}
      let outcome=sendOutcome(value);
      const observed=state.messages.find(message=>message.id===outgoing.id);
      if(outcome.state==='unknown' && observed)outcome={state:'saved',text:'已核到原消息 · 消息已保存，提醒结果以原回执为准。'};
      state.feedback=outcome.text;state.outcome=outcome.state;
      if(outcome.state==='saved'){
        Object.assign(state,acceptMessage(state,value.message||observed));state.pending=null;state.draft='';state.reply='';
        if(this.roomId===state.id){await this.$nextTick();this.scrollBottom();}
      }else if(outcome.state==='failed')state.pending=null;
      else if(state.pending)state.pending.sending=false;
      if(this.roomId===state.id && !state.pending){await this.$nextTick();this.$refs.input.focus();}
    },
    async checkPending() {
      const state=this.state;if(!state?.pending || state.pending.sending)return;
      this.checking=true;
      try {
        const room=checked(await request(endpoint(state.id)));
        Object.assign(state,readPage(state,room.messages));this.confirmPending(state);
        if(state.pending)state.feedback='暂未读到原消息。请稍后核对，保留输入并暂不重发。';
      }catch(error){state.feedback='核对未完成：'+error.message;}
      finally{this.checking=false;}
    },
    async openCreator() {
      this.sidebar=false;this.$refs.creator.showModal();
      try {await this.loadPeople();}catch(error){this.createError='无法读取同事：'+error.message;}
    },
    async createRoom() {
      if(this.creating || this.createUnknown)return;
      this.creating=true;this.createError='';this.createdRoomId='';
      let value;
      try {value=await request('/api/room',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({title:this.createTitle.trim(),members:this.createMembers})});}
      catch(error){value={ok:false,error:error.message};}
      this.creating=false;
      if(value.ok){this.$refs.creator.close();this.createTitle='';this.createMembers=[];await this.loadRooms();await this.selectRoom(value.room_id);}
      else {
        this.createdRoomId=value.room_id||'';
        this.createUnknown=!value.room_id && ![400,404,409,422].includes(value.status) &&
          !['cat_not_configured','cli_start_failed'].includes(value.error_code);
        this.createError=value.room_id?'房间已建立，但同事入座未全部完成。请打开该房间核对。':
          this.createUnknown?'创建结果未确认。请先刷新房间列表核对，暂不重复创建。':errorText(value);
      }
    },
  },
  async mounted() {
    document.documentElement.dataset.theme=this.theme;
    document.addEventListener('visibilitychange',()=>{if(document.hidden)this.stopStream();else if(this.state)this.startStream(this.state);});
    try {
      await Promise.all([this.loadRooms(),this.loadPeople()]);
      const wanted=new URLSearchParams(location.search).get('room');
      const first=this.rooms.find(room=>room.status==='open')||this.rooms[0];
      if(wanted||first)await this.selectRoom(wanted||first.id);else this.connection='已连接';
    }catch(error){this.connection='CAT暂不可用';this.connectionError=true;}
  },
  beforeUnmount() {this.stopStream();},
}).mount('#cat-app');
