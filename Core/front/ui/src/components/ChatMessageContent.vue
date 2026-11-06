<script>
import {markRaw} from 'vue';
import {renderMessage} from '../../../cat-content.mjs';
export default {
  props:{body:{type:String,required:true},expanded:Boolean,query:{type:String,default:''}},
  emits:['toggle','resize'],
  data(){return {overflow:false,observer:null};},
  computed:{html(){return renderMessage(this.body,this.query);}},
  methods:{
    measure(){
      const el=this.$refs.body;
      this.overflow=el.scrollHeight>parseFloat(getComputedStyle(el).getPropertyValue('--message-preview-height'));
      this.$emit('resize');
    },
  },
  watch:{body(){this.$nextTick(this.measure);}},
  mounted(){
    this.observer=markRaw(new ResizeObserver(this.measure));
    this.observer.observe(this.$refs.body);
  },
  beforeUnmount(){this.observer.disconnect();},
};

</script>
<template>
<div class="message-text" :class="{collapsed:!expanded,overflow:overflow}">
    <div ref="body" class="rich-text" v-html="html" @focusin="!expanded && overflow && $emit('toggle')"></div>
    <button v-if="overflow" class="expand-message" type="button" :aria-expanded="expanded" @click="$emit('toggle')">
      {{expanded?'收起长消息':'展开全文'}}
      <span aria-hidden="true">{{expanded?'↑':'↓'}}</span>
    </button>
  </div>
</template>
