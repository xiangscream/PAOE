<script>
import {markRaw} from 'vue';
import {readPage, acceptMessage, sendOutcome, errorText, seatLabels} from '../../../cat-state.mjs';
import {findMessages, messagePreview} from '../../../cat-content.mjs';
import CatIcon from './ChatIcon.vue';
import MessageContent from './ChatMessageContent.vue';
import {readDraft, writeDraft} from '../state/chat-drafts.mjs';

const dayFormat = new Intl.DateTimeFormat('zh-CN', {month:'long',day:'numeric',weekday:'short'});
const timeFormat = new Intl.DateTimeFormat('zh-CN', {hour:'2-digit',minute:'2-digit',hour12:false});
const endpoint = (id, suffix='') => '/api/room/' + encodeURIComponent(id) + suffix;
function newConversation(id) {
  return {id,title:'',status:'open',members:[],messages:[],cursor:0,draft:'',reply:'',pending:null,
          feedback:'',outcome:'',loaded:false,expanded:{},position:null,atLatest:true,firstUnseen:''};
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

export default {
  props:{project:{type:String,required:true},initialRoom:{type:String,default:''}},
  emits:['new-discussion','board'],
  components:{CatIcon, MessageContent},
  data() {
    return {rooms:[],people:[],roomStates:{},roomId:'',filter:'',roomScope:'open',sidebar:false,roomsLoading:true,
      seatLabels,selection:0,stream:null,storageError:'',
      connection:'正在连接',connectionError:false,unseen:0,highlight:'',checking:false,atLatest:true,
      searchOpen:false,searchQuery:'',searchIndex:0,searchReturn:null,refreshing:false};
  },
  computed: {
    state() { return this.roomStates[this.roomId] || null; },
    reply() { return this.state?.messages.find(message=>message.id===this.state.reply); },
    searchResults() { return findMessages(this.state?.messages || [],this.searchQuery); },
    searchStatus() {
      return !this.searchQuery.trim()?'搜索当前房间的原消息':this.searchResults.length?
        (this.searchIndex+1)+' / '+this.searchResults.length+' 条':'没有匹配的消息';
    },
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
    initialRoom(id) {if(id)this.selectRoom(id);},
    searchQuery() {this.searchIndex=0;this.highlight='';this.locateSearchResult();},
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
    avatarTone(id) {
      return id==='human'?'tone-human':'tone-'+(this.state.members.findIndex(member=>member.home_id===id)%5);
    },
    quote(id) {
      const message=this.state?.messages.find(item=>item.id===id);
      return message ? this.name(message.sender_id)+'：'+this.preview(message.body) : '回复较早的消息';
    },
    preview:messagePreview,
    persistDraft(state) {
      try {writeDraft(localStorage,state);this.storageError='';return true;}
      catch(error){this.storageError='草稿无法保存在此浏览器：'+error.message;return false;}
    },
    setDraft(value) { if(this.state){this.state.draft=value;this.persistDraft(this.state);}this.$nextTick(this.resizeComposer); },
    resizeComposer() {
      const pin=this.atLatest&&!this.searchOpen;
      const input=this.$refs.input;
      if(!input)return; // A pending receipt can finish after navigation.
      const limit=parseFloat(getComputedStyle(input).maxHeight);
      input.style.height='auto';
      input.style.height=Math.min(input.scrollHeight,limit)+'px';
      input.style.overflowY=input.scrollHeight>limit?'auto':'hidden';
      this.$nextTick(()=>{if(pin&&!this.searchOpen)this.scrollBottom();});
    },
    closeSidebarFromContent() { this.sidebar=false; },
    nearEnd() { const el=this.$refs.messages; return el.scrollHeight-el.scrollTop-el.clientHeight<100; },
    scrollBottom() {
      const el=this.$refs.messages;el.scrollTop=el.scrollHeight;this.unseen=0;this.atLatest=true;
      if(this.state)this.state.firstUnseen='';
    },
    onScroll() {
      this.atLatest=this.nearEnd();
      if(this.atLatest){this.unseen=0;if(this.state)this.state.firstUnseen='';}
    },
    messageElement(id) {
      return [...this.$refs.messages.querySelectorAll('[data-message-id]')].find(node=>node.dataset.messageId===id);
    },
    readingPosition() {
      const box=this.$refs.messages,top=box.getBoundingClientRect().top;
      const first=[...box.querySelectorAll('[data-message-id]')].find(node=>node.getBoundingClientRect().bottom>top);
      return first?{id:first.dataset.messageId,offset:first.getBoundingClientRect().top-top}:null;
    },
    restorePosition(position) {
      if(!position)return;
      const box=this.$refs.messages;
      const target=this.messageElement(position.id);
      if(target)box.scrollTop+=target.getBoundingClientRect().top-box.getBoundingClientRect().top-position.offset;
      this.onScroll();
    },
    onMessageResize() {
      this.$nextTick(()=>{if(this.atLatest&&!this.searchOpen)this.scrollBottom();});
    },
    async toggleMessage(id) {
      const position=this.readingPosition(),expanding=!this.state.expanded[id];this.atLatest=false;
      this.state.expanded[id]=expanding;
      await this.$nextTick();
      if(expanding)this.restorePosition(position);
      else {this.messageElement(id).scrollIntoView({block:'start'});this.onScroll();}
    },
    openMembers() {this.sidebar=false;this.$refs.memberDialog.showModal();},
    async openSearch() {
      this.searchReturn=this.readingPosition();this.searchOpen=true;this.sidebar=false;
      await this.$nextTick();this.$refs.messageSearch.focus();
    },
    async closeSearch() {
      this.searchOpen=false;this.searchQuery='';this.highlight='';
      await this.$nextTick();this.restorePosition(this.searchReturn);this.$refs.searchButton.focus();
    },
    locateSearchResult() {
      if(this.searchQuery.trim()&&this.searchResults.length)this.jumpTo(this.searchResults[this.searchIndex].id);
    },
    stepSearch(direction) {
      if(!this.searchResults.length)return;
      this.searchIndex=(this.searchIndex+direction+this.searchResults.length)%this.searchResults.length;
      this.locateSearchResult();
    },
    replyTo(id) { if (this.canCompose) {this.state.reply=id;this.persistDraft(this.state);this.$nextTick(()=>{this.resizeComposer();this.$refs.input.focus();});} },
    cancelReply() { if (this.canCompose) {this.state.reply='';this.persistDraft(this.state);} this.$nextTick(()=>{this.resizeComposer();this.$refs.input.focus();}); },
    async jumpTo(id) {
      const state=this.state;state.expanded[id]=true;this.atLatest=false;
      await this.$nextTick();
      if(this.state!==state)return;
      const target=this.messageElement(id);
      if(target){
        const hit=this.searchOpen?target.querySelector('.rich-text mark'):null;
        (hit||target).scrollIntoView({block:'center'});this.highlight=id;
        setTimeout(()=>{if(this.highlight===id&&!this.searchOpen)this.highlight='';},1800);
      }
    },
    confirmPending(state) {
      // A stream event may precede the POST receipt. Keep the composer owned
      // by that request until it settles, so its receipt cannot clear a new draft.
      if (!state.pending || state.pending.sending || !state.messages.some(message=>message.id===state.pending.id)) return;
      state.pending=null;state.draft='';state.reply='';state.outcome='saved';
      state.feedback='已核到原消息 · 消息已保存，提醒结果以原回执为准。';
      this.persistDraft(state);
      if(this.state===state)this.$nextTick(this.resizeComposer);
    },
    async loadRooms() {
      this.roomsLoading=true;
      try {this.rooms=checked(await request('/api/cat/rooms')).rooms;return this.rooms;}
      finally {this.roomsLoading=false;}
    },
    async loadPeople() { this.people=checked(await request('/api/cat/people')).people; },
    async selectRoom(id) {
      this.sidebar=false;
      if (this.roomId===id && this.state?.loaded) return;
      if(this.state){this.state.position=this.readingPosition();this.state.atLatest=this.atLatest;}
      this.searchOpen=false;this.searchQuery='';this.searchReturn=null;this.highlight='';
      this.stopStream(); const generation=++this.selection;
      if (!this.roomStates[id]) {
        const state=newConversation(id);
        try {Object.assign(state,readDraft(localStorage,id));}
        catch(error){this.storageError='无法恢复此房间的草稿：'+error.message;}
        if(state.pending){state.outcome='unknown';state.feedback='上次发送结果尚未确认，正在核对原消息。';}
        this.roomStates[id]=state;
      }
      this.roomId=id;const state=this.state,summary=this.rooms.find(room=>room.id===id);
      this.atLatest=state.atLatest;
      this.$nextTick(this.resizeComposer);
      if (summary) {state.title=summary.title;state.status=summary.status;this.roomScope=summary.status;}
      const url=new URL(location.href);url.searchParams.set('room',id);history.replaceState(null,'',url);
      this.connection='正在读取';this.connectionError=false;this.unseen=0;
      try {
        const room=checked(await request(endpoint(id)));
        Object.assign(state,{title:room.title,status:room.status,members:room.members,loaded:true},readPage(state,room.messages));
        this.confirmPending(state);
        if (generation!==this.selection) return;
        this.roomScope=room.status;document.title=(room.title||'圆桌')+' · CAT';
        await this.$nextTick();this.resizeComposer();
        if(state.atLatest)this.scrollBottom();else this.restorePosition(state.position);
        this.startStream(state);
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
        const update=JSON.parse(event.data),near=this.nearEnd()&&!this.searchOpen,count=state.messages.length;
        const seen=new Set(state.messages.map(message=>message.id));
        const firstNew=update.messages.find(message=>!seen.has(message.id));
        if(!near&&firstNew&&!state.firstUnseen)state.firstUnseen=firstNew.id;
        Object.assign(state,readPage(state,update.messages),{title:update.title,status:update.status,members:update.members});
        this.confirmPending(state);
        const summary=this.rooms.find(room=>room.id===state.id);
        if(summary){summary.title=state.title;summary.status=state.status;summary.message_count=state.messages.length;summary.member_count=state.members.length;}
        this.connection='实时连接';this.connectionError=false;
        await this.$nextTick();
        if(this.roomId!==state.id)return;
        if(near)this.scrollBottom();else {this.unseen+=Math.max(0,state.messages.length-count);this.onScroll();}
      });
      stream.onerror=()=>{
        if(this.stream!==stream)return;
        this.connection='实时连接中断 · 正在重连';this.connectionError=true;
      };
    },
    async refresh() {
      if(this.refreshing)return;
      this.refreshing=true;
      try {
        await Promise.all([this.loadRooms(),this.loadPeople()]);
        if(this.state) {
          const state=this.state,room=checked(await request(endpoint(state.id)));
          Object.assign(state,{title:room.title,status:room.status,members:room.members,loaded:true},readPage(state,room.messages));
          this.confirmPending(state);this.startStream(state);
        }else await this.openInitialRoom();
      } catch(error) {this.connection=error.message;this.connectionError=true;}
      finally{this.refreshing=false;this.$nextTick(this.resizeComposer);}
    },
    async openInitialRoom() {
      const wanted=this.initialRoom || new URLSearchParams(location.search).get('room');
      const first=this.rooms.find(room=>room.status==='open')||this.rooms[0];
      if(wanted||first)await this.selectRoom(wanted||first.id);else this.connection='已连接';
    },
    onVisibility() {if(document.hidden)this.stopStream();else if(this.state?.loaded)this.startStream(this.state);},
    onComposerKey(event) {
      if(!event.isComposing && (event.ctrlKey||event.metaKey) && event.key==='Enter'){event.preventDefault();this.send();}
    },
    async send() {
      if(!this.canSend)return;
      const state=this.state,outgoing={id:'human-'+crypto.randomUUID(),body:state.draft.trim(),reply:state.reply,sending:true};
      state.pending=outgoing;
      if(!this.persistDraft(state)){state.pending=null;state.feedback='发送前未能保存请求，请先恢复浏览器存储。';state.outcome='failed';return;}
      state.feedback='正在保存消息…';state.outcome='';
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
      this.persistDraft(state);
      if(this.roomId===state.id && !state.pending){await this.$nextTick();this.resizeComposer();this.$refs.input?.focus();}
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
    openCreator() {this.sidebar=false;this.$emit('new-discussion');},
  },
  async mounted() {
    document.addEventListener('visibilitychange',this.onVisibility);
    window.addEventListener('resize',this.resizeComposer);
    this.resizeComposer();
    try {
      await Promise.all([this.loadRooms(),this.loadPeople()]);
      await this.openInitialRoom();
    }catch(error){this.connection='CAT暂不可用';this.connectionError=true;}
  },
  beforeUnmount() {
    this.stopStream();this.selection++;this.roomId='';window.removeEventListener('resize',this.resizeComposer);
    document.removeEventListener('visibilitychange',this.onVisibility);
  },
};

</script>

<template>
<div class="cat-workspace">
  <aside class="rooms-panel" :class="{open:sidebar}" aria-label="房间列表">
    <div class="brand"><span class="brand-mark"><cat-icon name="room"></cat-icon></span><div><strong>CAT</strong><span>一起讨论，及时接话</span></div><button class="icon-button sidebar-close" aria-label="关闭房间列表" @click="sidebar=false"><cat-icon name="close"></cat-icon></button></div>
    <button class="primary-button new-discussion" @click="openCreator"><cat-icon name="plus"></cat-icon>新建讨论</button>
    <div class="room-list-heading"><span>你的讨论</span><button class="icon-button small" :class="{spinning:roomsLoading}" :disabled="refreshing" aria-label="刷新房间" @click="refresh"><cat-icon name="refresh"></cat-icon></button></div>
    <div class="room-tabs" role="group" aria-label="房间范围">
      <button :class="{selected:roomScope==='open'}" @click="roomScope='open'" :aria-pressed="roomScope==='open'">进行中</button>
      <button :class="{selected:roomScope==='closed'}" @click="roomScope='closed'" :aria-pressed="roomScope==='closed'">已结束</button>
    </div>
    <label class="search-field room-search"><cat-icon name="search"></cat-icon><input v-model="filter" type="search" placeholder="查找房间" aria-label="查找房间"></label>
    <nav class="room-list" aria-label="选择房间">
      <div v-if="!filteredRooms.length" class="empty-room-list">
        <p>{{roomsLoading?'正在读取讨论…':filter?'没有找到这个房间':'这里还没有讨论'}}</p>
        <button v-if="filter" class="text-button" @click="filter=''">清空搜索</button>
      </div>
      <button v-for="item in filteredRooms" :key="item.id" class="room-item" :class="{selected:item.id===roomId}" @click="selectRoom(item.id)" :aria-pressed="item.id===roomId">
        <span class="room-item-icon"><cat-icon name="room"></cat-icon></span><span class="room-item-text"><strong>{{item.title || '未命名圆桌'}}</strong><small>{{item.member_count}} 位同桌 <span>·</span> {{item.message_count}} 条消息</small></span>
      </button>
    </nav>
    <footer class="sidebar-footer"><span>想法在这里碰面</span><button class="text-button" @click="$emit('board')">返回画板<cat-icon name="external" /></button></footer>
  </aside>
  <button v-if="sidebar" class="sidebar-scrim" aria-label="收起房间列表" @click="sidebar=false"></button>
  <main class="conversation" @click="closeSidebarFromContent">
    <header class="conversation-header">
      <button class="icon-button mobile-menu" aria-label="展开房间列表" :aria-expanded="sidebar" @click.stop="sidebar=!sidebar"><cat-icon name="menu"></cat-icon></button>
      <div class="room-heading"><h1 :title="state?.title">{{state?.title || 'CAT 圆桌'}}</h1><div class="room-subtitle"><span :class="{'closed-label':state?.status==='closed'}">{{state?.status==='closed'?'已结束的讨论':state?'公开讨论':'选一个话题，开始交流'}}</span><span class="connection" :class="{error:connectionError,live:connection==='实时连接'}" role="status"><i></i>{{connectionError?'连接中断':connection}}</span></div></div>
      <div class="header-actions">
        <button ref="searchButton" class="icon-button" :class="{active:searchOpen}" :disabled="!state?.loaded" aria-label="搜索消息" :aria-expanded="searchOpen" @click="searchOpen?closeSearch():openSearch()"><cat-icon name="search"></cat-icon></button>
        <button class="members-button" :disabled="!state?.loaded" :aria-label="state?.loaded?'查看 '+state.members.length+' 位同桌':'同桌详情'" @click="openMembers"><cat-icon name="people"></cat-icon><span v-if="state?.loaded">{{state.members.length}}<span class="desktop-only"> 位同桌</span></span><span v-else class="desktop-only">同桌</span></button>
      </div>
    </header>
    <div v-if="searchOpen" class="message-search" role="search">
      <label class="search-field"><cat-icon name="search"></cat-icon><input ref="messageSearch" type="search" maxlength="200" v-model="searchQuery" aria-label="搜索本房间消息" placeholder="搜索本房间消息…" @keydown.enter.prevent="stepSearch($event.shiftKey?-1:1)" @keydown.esc.prevent="closeSearch"></label>
      <span class="search-count" role="status" aria-live="polite">{{searchStatus}}</span>
      <div class="search-actions"><button class="icon-button small" aria-label="上一条搜索结果" :disabled="!searchResults.length" @click="stepSearch(-1)"><cat-icon name="up"></cat-icon></button><button class="icon-button small" aria-label="下一条搜索结果" :disabled="!searchResults.length" @click="stepSearch(1)"><cat-icon name="down"></cat-icon></button><button class="icon-button small" aria-label="关闭消息搜索" @click="closeSearch"><cat-icon name="close"></cat-icon></button></div>
    </div>
    <div v-if="connectionError" class="connection-banner" role="alert"><div><strong>暂时无法取得新消息</strong><span>{{state?.loaded?'已显示的消息和草稿保留，连接恢复后会继续更新。':'请重新连接后再打开讨论。'}}</span></div><button class="secondary-button small" :disabled="refreshing" @click="refresh"><cat-icon name="refresh"></cat-icon>{{refreshing?'连接中…':'重新连接'}}</button></div>
    <div class="timeline-area">
      <section ref="messages" class="messages" aria-label="按时间排列的消息" tabindex="0" @scroll="onScroll">
        <div v-if="!state || !state.loaded || !state.messages.length" class="welcome"><span class="welcome-mark"><cat-icon name="room"></cat-icon></span><h2>{{connectionError?'稍后再继续这场讨论':state&&!state.loaded?'正在打开讨论…':state?'讨论从这里开始':'找个话题，坐下来聊聊'}}</h2><p>{{connectionError?'连接恢复后，原消息仍在这里。':state&&!state.loaded?'正在读取原房间和历史消息。':state?'写下一个问题，或分享一个想法。':'从左侧打开已有房间，或邀请同事开启新讨论。'}}</p><button v-if="!state&&!roomsLoading&&!connectionError" class="primary-button" @click="openCreator"><cat-icon name="plus"></cat-icon>新建讨论</button></div>
        <div class="message-column">
          <template v-for="(message,index) in state?.messages || []" :key="message.id">
            <div v-if="index===0 || day(message.created_at)!==day(state.messages[index-1].created_at)" class="day-divider"><span>{{day(message.created_at)}}</span></div>
            <div v-if="state.firstUnseen===message.id" class="unread-divider" role="separator" aria-label="以下是新消息"><span>以下是新消息</span></div>
            <article class="message" :class="{own:message.sender_id==='human',highlight:highlight===message.id}" :data-message-id="message.id">
              <span class="avatar" :class="avatarTone(message.sender_id)" aria-hidden="true">{{avatar(message.sender_id)}}</span>
              <div class="message-content">
                <div class="message-meta"><strong :title="name(message.sender_id)">{{name(message.sender_id)}}</strong><time :datetime="message.created_at" :title="day(message.created_at)+' '+time(message.created_at)">{{time(message.created_at)}}</time><button class="reply-action" :aria-label="'回复 '+name(message.sender_id)+' 的这条消息'" :disabled="!canCompose" @click="replyTo(message.id)"><cat-icon name="reply"></cat-icon><span>回复</span></button></div>
                <button v-if="message.reply_to" class="quote" title="定位原消息" @click="jumpTo(message.reply_to)"><cat-icon name="reply"></cat-icon><span>{{quote(message.reply_to)}}</span></button>
                <message-content :body="message.body" :query="searchOpen?searchQuery:''" :expanded="!!state.expanded[message.id]" @toggle="toggleMessage(message.id)" @resize="onMessageResize"></message-content>
              </div>
            </article>
          </template>
        </div>
      </section>
      <div class="latest-jump"><button v-if="!atLatest || unseen" class="latest-button" @click="scrollBottom"><cat-icon name="latest"></cat-icon><span>{{unseen?unseen+' 条新消息':'回到最新'}}</span></button></div>
    </div>
    <section class="composer" aria-label="发言">
      <div class="composer-inner">
        <p v-if="storageError" class="form-error" role="alert">{{storageError}}</p>
        <div v-if="reply" class="reply-bar" id="reply-bar"><cat-icon name="reply"></cat-icon><div><strong>回复 {{name(reply.sender_id)}}</strong><p>{{preview(reply.body)}}</p></div><button type="button" id="cancel-reply" class="icon-button small" aria-label="取消回复" :disabled="!canCompose" @click.stop="cancelReply"><cat-icon name="close"></cat-icon></button></div>
        <form @submit.prevent="send">
          <label class="sr-only" for="message-input">发言内容</label>
          <textarea id="message-input" ref="input" :value="state?.draft || ''" @input="setDraft($event.target.value)" rows="1" maxlength="20000" :disabled="!canCompose" :placeholder="placeholder" @keydown="onComposerKey"></textarea>
          <div class="composer-footer"><span class="identity"><span class="human-dot"></span>你 · Human</span><div class="send-actions"><span class="keyboard-hint">Ctrl / ⌘ + Enter</span><button class="primary-button send-button" type="submit" :disabled="!canSend"><span>{{state?.pending?.sending?'发送中':'发送'}}</span><cat-icon name="send"></cat-icon></button></div></div>
        </form>
        <div v-if="state?.feedback" class="send-feedback"><p :class="state.outcome" role="status" aria-live="polite">{{state.feedback}}</p><button v-if="state.pending && !state.pending.sending" class="text-button" :disabled="checking" @click="checkPending">{{checking?'核对中…':'核对原消息'}}</button></div>
      </div>
    </section>
  </main>
  <dialog ref="memberDialog" class="modal side-modal" aria-labelledby="members-title">
    <section class="modal-box member-sheet"><header class="dialog-heading"><div><span class="eyebrow">这场讨论</span><h2 id="members-title">{{state?.members.length || 0}} 位同桌</h2></div><button class="icon-button" aria-label="关闭同桌详情" @click="$refs.memberDialog.close()"><cat-icon name="close"></cat-icon></button></header><p class="dialog-description">成员和参与状态来自当前房间。</p>
      <div class="member-list"><div v-for="member in state?.members || []" :key="member.home_id" class="member-row"><span class="avatar" :class="avatarTone(member.home_id)">{{avatar(member.home_id)}}</span><strong>{{name(member.home_id)}}</strong><span class="seat-status" :class="'seat-'+member.state">{{seatLabels[member.state] || member.state}}</span></div></div>
      <footer class="member-note">旁听者可以阅读讨论，不接收新消息提醒。</footer>
    </section>
    <form method="dialog" class="modal-backdrop"><button aria-label="关闭成员抽屉">关闭</button></form>
  </dialog>
</div>
</template>

<style scoped>
button,input,textarea,select{font:inherit}
button,a,input,textarea,select{-webkit-tap-highlight-color:transparent}
button{cursor:pointer}
button:disabled{cursor:default;opacity:.42}
a{color:var(--color-primary)}
button:focus-visible,a:focus-visible,select:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--color-primary);outline-offset:3px}
.icon{width:20px;height:20px;flex-shrink:0;vertical-align:middle}
.cat-workspace{--color-primary:var(--accent);--color-primary-content:#fff;--color-base-100:var(--surface);--color-base-200:var(--paper);--color-base-300:var(--line);--color-base-content:var(--ink);--color-warning:#b47923;--color-error:#c34545;--color-success:var(--jade);height:100%;min-height:0;position:relative;display:grid;grid-template-columns:274px minmax(0,1fr);background:var(--color-base-100);color:var(--color-base-content);font-size:14px}
.primary-button,.secondary-button,.icon-button,.text-button,.members-button,.latest-button{display:inline-flex;align-items:center;justify-content:center;gap:8px;border:1px solid transparent;line-height:1.3;white-space:nowrap;transition:background .15s,border-color .15s}
.primary-button{background:var(--color-primary);color:var(--color-primary-content);border-color:var(--color-primary);border-radius:10px;min-height:40px;padding:9px 16px;font-size:13px;font-weight:600;box-shadow:0 1px 2px #0001}
.primary-button:hover:not(:disabled){filter:brightness(1.06)}
.primary-button:disabled{background:var(--color-base-300);border-color:var(--color-base-300);color:var(--color-base-content);box-shadow:none;opacity:.6}
.secondary-button{background:var(--color-base-100);color:inherit;border-color:var(--color-base-300);border-radius:10px;min-height:40px;padding:9px 15px;font-size:13px}
.secondary-button:hover:not(:disabled),.icon-button:hover:not(:disabled){background:var(--color-base-200)}
.icon-button{width:40px;height:40px;border-radius:10px;background:transparent;color:inherit}
.icon-button.small{width:32px;height:32px;border-radius:8px}
.icon-button.small .icon{width:17px;height:17px}
.icon-button.active{background:color-mix(in oklch,var(--color-primary) 10%,var(--color-base-100));color:var(--color-primary)}
.text-button{background:transparent;color:var(--color-primary);padding:5px 0;font-size:13px}
.text-button:hover{text-decoration:underline;text-underline-offset:3px}
.small.secondary-button{min-height:34px;font-size:12px;padding:7px 11px}
.spinning .icon{animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

.rooms-panel{display:flex;flex-direction:column;min-height:0;padding:24px 16px 16px;background:var(--color-base-200);border-right:1px solid var(--color-base-300)}
.brand{display:flex;align-items:center;gap:11px;padding:0 4px;margin-bottom:26px}
.brand-mark{display:grid;place-items:center;width:39px;height:39px;background:var(--color-primary);color:var(--color-primary-content);border-radius:13px 13px 13px 4px;box-shadow:0 3px 9px color-mix(in oklch,var(--color-primary) 15%,transparent)}
.brand-mark .icon{width:23px;height:23px}
.brand>div{display:grid;gap:3px}
.brand strong{font-size:19px;letter-spacing:.8px;line-height:1.2;font-weight:700}
.brand>div>span{font-size:11px;opacity:.58}
.new-discussion{width:100%;margin-bottom:24px;min-height:42px}
.room-list-heading{display:flex;align-items:center;justify-content:space-between;padding:0 6px;margin-bottom:7px;font-size:12px;font-weight:600;color:color-mix(in oklch,var(--color-base-content) 66%,transparent)}
.room-tabs{display:flex;gap:4px;padding:3px;background:color-mix(in oklch,var(--color-base-300) 72%,transparent);border-radius:9px;margin-bottom:12px}
.room-tabs button{flex:1;padding:7px 10px;border:0;border-radius:7px;background:transparent;color:inherit;font-size:12px;opacity:.66}
.room-tabs button.selected{background:var(--color-base-100);box-shadow:0 1px 4px #0001;opacity:1;font-weight:600}
.search-field{display:flex;align-items:center;gap:8px;border:1px solid var(--color-base-300);background:var(--color-base-100);border-radius:9px;padding:9px 11px;min-width:0}
.search-field>.icon{width:16px;height:16px;opacity:.5}
.search-field input{width:100%;min-width:0;border:0;outline:0;background:transparent;color:inherit;font-size:13px;line-height:20px}
.search-field:focus-within{border-color:var(--color-primary);box-shadow:0 0 0 2px color-mix(in oklch,var(--color-primary) 10%,transparent)}
.room-search{margin-bottom:14px}
.room-list{flex:1;min-height:0;overflow:auto;margin:0 -7px;padding:0 7px;scrollbar-width:thin}
.room-item{width:100%;display:flex;align-items:flex-start;gap:10px;padding:13px 11px;margin-bottom:5px;border:1px solid transparent;border-radius:11px;background:transparent;color:inherit;text-align:left}
.room-item:hover{background:color-mix(in oklch,var(--color-base-300) 65%,transparent)}
.room-item.selected{background:color-mix(in oklch,var(--color-primary) 9%,var(--color-base-100));border-color:color-mix(in oklch,var(--color-primary) 15%,transparent)}
.room-item-icon{display:grid;place-items:center;width:28px;height:28px;flex-shrink:0;border-radius:8px;background:var(--color-base-100);color:color-mix(in oklch,var(--color-base-content) 54%,transparent)}
.room-item-icon .icon{width:16px;height:16px}
.room-item.selected .room-item-icon{background:color-mix(in oklch,var(--color-primary) 12%,var(--color-base-100));color:var(--color-primary)}
.room-item-text{min-width:0;display:block}
.room-item strong{font-size:13px;line-height:1.6;font-weight:600;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.room-item small{display:block;font-size:11px;opacity:.55;line-height:1.5;margin-top:6px}
.room-item small span{margin:0 3px}
.empty-room-list{padding:25px 12px;text-align:center;font-size:13px;opacity:.75}
.empty-room-list p{line-height:1.7;margin:0 0 8px}
.sidebar-footer{display:flex;align-items:center;justify-content:space-between;gap:10px;border-top:1px solid var(--color-base-300);padding-top:17px;margin-top:16px}
.sidebar-footer label,.board-link{display:flex;align-items:center;gap:6px}
.sidebar-footer label>.icon{width:16px;height:16px;opacity:.6}
.sidebar-footer select{background:transparent;border:0;border-radius:5px;color:inherit;font-size:12px;padding:4px;max-width:90px}
.board-link{font-size:12px;text-decoration:none;opacity:.7;color:inherit}
.board-link:hover{opacity:1;color:var(--color-primary)}
.board-link .icon{width:13px;height:13px}

.conversation{display:flex;flex-direction:column;min-height:0;min-width:0;position:relative}
.conversation-header{display:flex;align-items:center;gap:12px;padding:18px 28px 17px;border-bottom:1px solid var(--color-base-300);flex-shrink:0}
.room-heading{flex:1;min-width:0}
.room-heading h1{font-size:18px;font-weight:650;letter-spacing:-.3px;line-height:1.5;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.room-subtitle{display:flex;align-items:center;gap:14px;margin-top:5px;font-size:11px;color:color-mix(in oklch,var(--color-base-content) 59%,transparent)}
.connection{display:inline-flex;align-items:center;gap:5px;font-size:11px;white-space:nowrap}
.connection i{width:5px;height:5px;display:block;border-radius:50%;background:var(--color-base-content);opacity:.35}
.connection.live i{background:#3b9d79;opacity:1;box-shadow:0 0 0 3px #3b9d790e}
.connection.error{color:var(--color-warning)}
.connection.error i{background:var(--color-warning);opacity:1}
.closed-label{color:var(--color-base-content)}
.header-actions{display:flex;align-items:center;gap:6px}
.members-button{min-height:38px;padding:8px 12px;border-radius:10px;color:inherit;background:var(--color-base-100);border-color:var(--color-base-300);font-size:12px}
.members-button .icon{width:17px;height:17px;opacity:.7}
.members-button:hover:not(:disabled){background:var(--color-base-200)}
.message-search{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:12px;padding:11px 28px;border-bottom:1px solid var(--color-base-300);background:var(--color-base-200)}
.message-search .search-field{padding-block:7px}
.search-count{font-size:12px;color:color-mix(in oklch,var(--color-base-content) 64%,transparent);white-space:nowrap}
.search-actions{display:flex;align-items:center;gap:2px}
.connection-banner{display:flex;align-items:center;justify-content:space-between;gap:15px;padding:12px 28px;background:color-mix(in oklch,var(--color-warning) 9%,var(--color-base-100));border-bottom:1px solid color-mix(in oklch,var(--color-warning) 20%,var(--color-base-300))}
.connection-banner>div{display:grid;gap:4px}
.connection-banner strong{font-size:13px;font-weight:600}
.connection-banner span{font-size:12px;line-height:1.5;opacity:.7}

.timeline-area{flex:1;min-height:0;position:relative}
.messages{height:100%;overflow:auto;overscroll-behavior:contain;padding:24px 32px 28px;scrollbar-width:thin;scrollbar-gutter:stable;scrollbar-color:color-mix(in oklch,var(--color-base-content) 18%,transparent) transparent}
.message-column{max-width:850px;margin:0 auto}
.message{--message-surface:var(--color-base-100);display:grid;grid-template-columns:36px minmax(0,1fr);gap:13px;margin-bottom:27px;scroll-margin:30px}
.avatar{width:36px;height:36px;display:grid;place-items:center;flex-shrink:0;border-radius:12px;background:var(--color-base-200);color:var(--color-base-content);font-size:10px;font-weight:650;white-space:nowrap;letter-spacing:-.2px}
.tone-0{background:color-mix(in oklch,#4986ac 14%,var(--color-base-100));color:color-mix(in oklch,#4986ac 75%,var(--color-base-content))}
.tone-1{background:color-mix(in oklch,#8d71bd 14%,var(--color-base-100));color:color-mix(in oklch,#8d71bd 75%,var(--color-base-content))}
.tone-2{background:color-mix(in oklch,#518f7d 14%,var(--color-base-100));color:color-mix(in oklch,#518f7d 75%,var(--color-base-content))}
.tone-3{background:color-mix(in oklch,#b98547 14%,var(--color-base-100));color:color-mix(in oklch,#b98547 75%,var(--color-base-content))}
.tone-4{background:color-mix(in oklch,#b56f87 14%,var(--color-base-100));color:color-mix(in oklch,#b56f87 75%,var(--color-base-content))}
.tone-human{background:var(--color-primary);color:var(--color-primary-content)}
.message-content{min-width:0}
.message-meta{display:flex;align-items:center;gap:10px;min-height:27px;margin-bottom:5px}
.message-meta strong{font-size:13px;font-weight:650;max-width:65%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.message-meta time{font-size:11px;color:color-mix(in oklch,var(--color-base-content) 46%,transparent);white-space:nowrap}
.reply-action{display:inline-flex;align-items:center;gap:5px;flex-shrink:0;margin-left:auto;padding:5px 7px;background:transparent;border:0;border-radius:6px;font-size:11px;color:color-mix(in oklch,var(--color-base-content) 65%,transparent);opacity:0}
.reply-action .icon{width:14px;height:14px}
.message:hover .reply-action,.message:focus-within .reply-action,.reply-action:focus-visible{opacity:1}
.reply-action:hover:not(:disabled){background:var(--color-base-200);color:var(--color-primary)}
.quote{display:flex;align-items:flex-start;gap:8px;width:100%;text-align:left;margin:0 0 9px;padding:9px 11px;border:0;border-left:2px solid color-mix(in oklch,var(--color-primary) 60%,var(--color-base-300));border-radius:0 8px 8px 0;background:var(--color-base-200);color:color-mix(in oklch,var(--color-base-content) 65%,transparent);font-size:12px;line-height:1.6}
.quote>.icon{width:14px;height:14px;margin-top:2px;opacity:.7}
.quote>span{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.quote:hover{background:color-mix(in oklch,var(--color-primary) 6%,var(--color-base-200))}
:deep(.message-text){position:relative}
:deep(.rich-text){--message-preview-height:320px;font-size:15px;line-height:1.75;overflow-wrap:anywhere;color:var(--color-base-content)}
:deep(.rich-text>:first-child){margin-top:0}
:deep(.rich-text>:last-child){margin-bottom:0}
:deep(.rich-text p){margin:0 0 11px}
:deep(.rich-text ul),:deep(.rich-text ol){margin:8px 0 12px;padding-left:23px;list-style-position:outside}
:deep(.rich-text ul){list-style-type:disc}:deep(.rich-text ol){list-style-type:decimal}
:deep(.rich-text li){margin:4px 0}
:deep(.rich-text li>p){margin:3px 0}
:deep(.rich-text strong){font-weight:650}
:deep(.rich-text mark){background:color-mix(in oklch,#e5b83c 38%,var(--color-base-100));color:inherit;padding:0 1px;border-radius:2px}
:deep(.rich-text h1),:deep(.rich-text h2),:deep(.rich-text h3),:deep(.rich-text h4),:deep(.rich-text h5),:deep(.rich-text h6){font-size:1em;line-height:1.6;font-weight:650;margin:18px 0 8px}
:deep(.rich-text a){text-decoration:underline;text-underline-offset:3px;text-decoration-color:color-mix(in oklch,var(--color-primary) 35%,transparent)}
:deep(.rich-text a:hover){text-decoration-color:var(--color-primary)}
:deep(.rich-text code){font-family:"Cascadia Code",Consolas,monospace;font-size:.86em;padding:2px 5px;background:var(--color-base-200);border:1px solid var(--color-base-300);border-radius:5px;box-decoration-break:clone;-webkit-box-decoration-break:clone}
:deep(.rich-text pre){padding:13px 15px;margin:12px 0;background:var(--color-base-200);border:1px solid var(--color-base-300);border-radius:10px;overflow-x:auto;white-space:pre;line-height:1.7;scrollbar-width:thin}
:deep(.rich-text pre code){padding:0;border:0;background:transparent;border-radius:0;white-space:pre;overflow-wrap:normal}
:deep(.rich-text blockquote){border-left:3px solid var(--color-base-300);margin:12px 0;padding:0 0 0 14px;color:color-mix(in oklch,var(--color-base-content) 70%,transparent)}
:deep(.rich-text hr){border:0;border-top:1px solid var(--color-base-300);margin:16px 0}
:deep(.rich-text table){display:block;max-width:100%;overflow:auto;border-collapse:collapse;margin:12px 0;font-size:13px}
:deep(.rich-text th),:deep(.rich-text td){border:1px solid var(--color-base-300);padding:8px 12px;text-align:left;min-width:90px}
:deep(.rich-text th){background:var(--color-base-200);font-weight:600}
:deep(.message-text.collapsed .rich-text){max-height:var(--message-preview-height);overflow:hidden}
:deep(.message-text.collapsed.overflow::after){content:"";position:absolute;bottom:36px;left:0;right:0;height:42px;pointer-events:none;background:linear-gradient(transparent,var(--message-surface))}
:deep(.expand-message){position:relative;z-index:1;display:flex;align-items:center;gap:8px;margin:5px 0 0;padding:7px 0;border:0;background:transparent;color:var(--color-primary);font-size:12px;font-weight:600}
:deep(.expand-message:hover){text-decoration:underline;text-underline-offset:3px}
.message.own{--message-surface:color-mix(in oklch,var(--color-primary) 5%,var(--color-base-100))}
:deep(.message.own .message-text){padding:12px 15px;background:var(--message-surface);border:1px solid color-mix(in oklch,var(--color-primary) 12%,var(--color-base-300));border-radius:0 12px 12px 12px}
:deep(.message.own .message-text.collapsed.overflow::after){left:15px;right:15px;bottom:48px}
.day-divider,.unread-divider{display:flex;align-items:center;gap:14px;margin:4px 0 28px;font-size:11px;color:color-mix(in oklch,var(--color-base-content) 48%,transparent)}
.day-divider::before,.day-divider::after,.unread-divider::before,.unread-divider::after{content:"";height:1px;flex:1;background:var(--color-base-300)}
.day-divider span{padding:3px 10px;border:1px solid var(--color-base-300);border-radius:20px;background:var(--color-base-100)}
.unread-divider{color:var(--color-primary);margin:16px 0 22px}
.unread-divider::before,.unread-divider::after{background:color-mix(in oklch,var(--color-primary) 22%,var(--color-base-300))}
.message.highlight{background:color-mix(in oklch,var(--color-primary) 7%,var(--color-base-100));box-shadow:0 0 0 9px color-mix(in oklch,var(--color-primary) 7%,var(--color-base-100));border-radius:8px}
.latest-jump{position:absolute;bottom:16px;right:29px;pointer-events:none}
.latest-button{pointer-events:auto;padding:9px 14px;min-height:37px;border-radius:22px;border-color:var(--color-base-300);background:var(--color-base-100);color:var(--color-primary);box-shadow:0 4px 16px #00000012;font-size:12px;font-weight:600}
.latest-button .icon{width:16px;height:16px}
.latest-button:hover{border-color:var(--color-primary)}

.composer{padding:12px 32px 18px;flex-shrink:0;border-top:1px solid var(--color-base-300);background:var(--color-base-100)}
.composer-inner{max-width:850px;margin:auto}
.composer form{padding:13px 15px 10px;border:1px solid var(--color-base-300);border-radius:13px;background:var(--color-base-100);box-shadow:0 2px 8px #00000004}
.composer form:focus-within{border-color:color-mix(in oklch,var(--color-primary) 55%,var(--color-base-300));box-shadow:0 0 0 3px color-mix(in oklch,var(--color-primary) 7%,transparent)}
.composer textarea{display:block;width:100%;min-height:25px;max-height:180px;padding:0;border:0;outline:0;background:transparent;color:inherit;font-size:15px;line-height:25px;resize:none;box-shadow:none;overflow-y:hidden}
.composer textarea::placeholder{color:color-mix(in oklch,var(--color-base-content) 42%,transparent)}
.composer-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:9px}
.identity{display:inline-flex;align-items:center;gap:7px;color:color-mix(in oklch,var(--color-base-content) 52%,transparent);font-size:11px}
.human-dot{display:block;width:6px;height:6px;background:var(--color-primary);border-radius:50%;opacity:.55}
.send-actions{display:flex;align-items:center;gap:12px}
.keyboard-hint{font-size:10px;color:color-mix(in oklch,var(--color-base-content) 40%,transparent)}
.send-button{min-height:32px;padding:7px 12px;border-radius:8px;font-size:12px;gap:8px}
.send-button .icon{width:14px;height:14px}
.send-feedback{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 2px 0}
.send-feedback p{margin:0;font-size:12px;line-height:1.5;color:color-mix(in oklch,var(--color-base-content) 64%,transparent)}
.send-feedback p.failed,.send-feedback p.unknown{color:var(--color-warning)}
.send-feedback p.saved{color:color-mix(in oklch,var(--color-success) 70%,var(--color-base-content))}
.send-feedback .text-button{padding:2px;font-size:12px;flex-shrink:0}
.reply-bar{display:flex;align-items:center;gap:10px;margin:0 0 9px;padding:10px 12px;border-radius:9px;background:var(--color-base-200);border-left:2px solid var(--color-primary);font-size:12px}
.reply-bar>.icon{width:16px;height:16px;color:var(--color-primary)}
.reply-bar>div{min-width:0;flex:1}
.reply-bar strong{font-weight:600;color:var(--color-primary)}
.reply-bar p{font-size:12px;line-height:1.5;margin:4px 0 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:.6}
.reply-bar button{flex-shrink:0}

.welcome{display:flex;height:100%;min-height:210px;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:28px 18px}
.welcome-mark{display:grid;place-items:center;width:66px;height:66px;border:1px solid color-mix(in oklch,var(--color-primary) 16%,var(--color-base-300));border-radius:22px;background:color-mix(in oklch,var(--color-primary) 7%,var(--color-base-100));color:var(--color-primary);margin-bottom:20px}
.welcome-mark .icon{width:30px;height:30px}
.welcome h2{font-size:19px;line-height:1.5;font-weight:600;margin:0 0 9px}
.welcome p{font-size:13px;line-height:1.8;max-width:310px;margin:0 0 22px;opacity:.55}
.modal-box{border:1px solid var(--color-base-300);background:var(--color-base-100);border-radius:18px;box-shadow:0 18px 70px #0002;padding:27px;max-height:calc(100dvh - 32px)}
.modal::backdrop{background:#11182745;backdrop-filter:blur(2px)}
.dialog-heading{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-bottom:22px}
.dialog-heading h2{font-size:22px;line-height:1.4;font-weight:650;margin:4px 0 0}
.eyebrow{font-size:11px;letter-spacing:.5px;opacity:.5}
.dialog-description{font-size:12px;line-height:1.7;margin:14px 0;color:color-mix(in oklch,var(--color-base-content) 60%,transparent)}
.side-modal{justify-items:end}
.member-sheet{height:calc(100dvh - 24px);max-height:none;width:min(390px,calc(100vw - 24px));max-width:none;margin:12px;display:flex;flex-direction:column}
.member-list{overflow:auto;min-height:0;flex:1;margin-top:5px}
.member-row{display:flex;align-items:center;gap:12px;padding:15px 0;border-bottom:1px solid color-mix(in oklch,var(--color-base-300) 65%,transparent)}
.member-row strong{flex:1;min-width:0;font-size:13px;font-weight:550;line-height:1.6;overflow-wrap:anywhere}
.seat-status{flex-shrink:0;font-size:11px;padding:4px 8px;border-radius:6px;background:var(--color-base-200);color:color-mix(in oklch,var(--color-base-content) 58%,transparent)}
.seat-participant{background:color-mix(in oklch,var(--color-primary) 9%,var(--color-base-100));color:var(--color-primary)}
.member-note{font-size:11px;line-height:1.7;opacity:.55;padding-top:17px}
.field-label{display:grid;gap:9px;font-size:13px;font-weight:600}
.field-label .input{width:100%;height:43px;background:var(--color-base-100);font-weight:400;font-size:14px;border-radius:10px;border:1px solid var(--color-base-300)}
.field-label .input:focus{outline:2px solid color-mix(in oklch,var(--color-primary) 15%,transparent);outline-offset:0;border-color:var(--color-primary)}
.people-list{display:grid;gap:7px;max-height:280px;overflow:auto}
.people-list label{display:flex;align-items:center;gap:12px;padding:11px 12px;background:var(--color-base-200);border:1px solid transparent;border-radius:10px;cursor:pointer}
.people-list label:has(input:checked){border-color:color-mix(in oklch,var(--color-primary) 30%,var(--color-base-300));background:color-mix(in oklch,var(--color-primary) 7%,var(--color-base-100))}
.people-list label>span{display:grid;gap:3px;min-width:0}
.people-list strong{font-size:12px;font-weight:600}
.people-list small{font-size:12px;opacity:.65;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.form-error{font-size:12px;line-height:1.7;color:var(--color-error);margin-top:15px}
.modal-action{margin-top:24px}
.mobile-menu,.sidebar-close,.sidebar-scrim{display:none}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}

@media(max-width:1050px){
  .cat-workspace{grid-template-columns:238px minmax(0,1fr)}
  .rooms-panel{padding-inline:12px}
  .conversation-header{padding-inline:22px}
  .messages{padding-inline:25px}
  .composer{padding-inline:24px}
  .message-search{padding-inline:22px;gap:7px}
  .search-count{font-size:11px}
}
@media(max-width:720px){
  .cat-workspace{display:block;border:0}
  .conversation{height:100%}
  .rooms-panel{display:none;position:absolute;inset:0 auto 0 0;width:min(310px,86vw);z-index:9;box-shadow:12px 0 40px #0002}
  .rooms-panel.open{display:flex}
  .sidebar-scrim{display:block;position:absolute;inset:0;border:0;background:#11182745;z-index:8}
  .mobile-menu,.sidebar-close{display:inline-flex}
  .sidebar-close{margin-left:auto}
  .brand{margin-top:3px}
  .conversation-header{padding:13px 15px 12px;gap:9px}
  .room-heading h1{font-size:17px}
  .room-subtitle{font-size:10px;gap:9px}
  .connection{font-size:10px}
  .header-actions{gap:2px}
  .desktop-only{display:none}
  .members-button{padding:8px 10px;min-height:38px;font-size:12px}
  .members-button .icon{width:17px;height:17px}
  .messages{padding:22px 20px 23px}
  .message{grid-template-columns:32px minmax(0,1fr);gap:11px;margin-bottom:25px}
  .avatar{width:32px;height:32px;font-size:9px;border-radius:10px}
  .message-meta strong{font-size:13px;max-width:63%}
  .message-meta time{font-size:10px}
:deep(  .rich-text){--message-preview-height:264px;font-size:14px;line-height:1.8}
  .quote{font-size:11px;padding:8px 10px}
  .composer{padding:10px 16px 13px}
  .composer form{padding:11px 12px 9px}
  .composer textarea{font-size:14px;line-height:24px;min-height:24px;max-height:144px}
  .keyboard-hint{display:none}
  .latest-jump{right:19px;bottom:13px}
  .message-search{grid-template-columns:minmax(0,1fr) auto;padding:10px 16px;gap:7px}
  .message-search .search-field{grid-column:1/-1}
  .search-count{min-width:0;font-size:11px}
  .search-actions{justify-content:flex-end}
  .connection-banner{padding:11px 16px;gap:10px}
  .connection-banner span{display:none}
  .connection-banner strong{font-size:12px}
  .modal-box{padding:22px}
  .dialog-heading h2{font-size:20px}
}
@media(hover:none){.reply-action{opacity:.65}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

</style>
