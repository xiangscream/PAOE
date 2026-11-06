<script>
const paths = {
  menu:['M4 6h16M4 12h16M4 18h16'],
  search:['M21 21l-5-5','M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0'],
  people:['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2','M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8','M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75'],
  plus:['M12 5v14M5 12h14'],
  close:['M6 6l12 12M18 6 6 18'],
  down:['m6 9 6 6 6-6'],
  up:['m6 15 6-6 6 6'],
  latest:['M12 3v15m-5-5 5 5 5-5M5 21h14'],
  send:['m22 2-7 20-4-9-9-4Z','M22 2 11 13'],
  reply:['m9 10-5 5 5 5','M4 15h10a6 6 0 0 0 0-12h-2'],
  refresh:['M20 7v5h-5','M4 17v-5h5','M6.1 6.1A8 8 0 0 1 19.8 10M4.2 14a8 8 0 0 0 13.7 3.9'],
  room:['M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z'],
  external:['M15 3h6v6M10 14 21 3','M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5'],
  sun:['M12 3V1m0 22v-2M3 12H1m22 0h-2M4.2 4.2 2.8 2.8m18.4 18.4-1.4-1.4M4.2 19.8l-1.4 1.4M21.2 2.8l-1.4 1.4','M17 12a5 5 0 1 1-10 0 5 5 0 0 1 10 0'],
};
export default {
  props:{name:{type:String,required:true}},
  computed:{paths(){return paths[this.name];}},
};
</script>
<template>
<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path v-for="(path,index) in paths" :key="index" :d="path"/></svg>
</template>
