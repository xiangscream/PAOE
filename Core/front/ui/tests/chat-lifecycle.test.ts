import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChatView from '../src/components/ChatView.vue'

afterEach(()=>vi.unstubAllGlobals())

it('leaving CAT while the list is loading cannot reopen a room or change the current URL',async()=>{
  let roomsDone!:(value:unknown)=>void
  let peopleDone!:(value:unknown)=>void
  const fetch=vi.fn()
    .mockReturnValueOnce(new Promise(resolve=>{roomsDone=resolve}))
    .mockReturnValueOnce(new Promise(resolve=>{peopleDone=resolve}))
  const events=vi.fn()
  vi.stubGlobal('fetch',fetch)
  vi.stubGlobal('EventSource',events)
  const wrapper=mount(ChatView,{props:{project:'1001',initialRoom:'original'}})
  const before=location.href
  wrapper.unmount()
  roomsDone({ok:true,json:async()=>({ok:true,rooms:[{id:'original',status:'open'}]})})
  peopleDone({ok:true,json:async()=>({ok:true,people:[]})})
  await flushPromises()
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(events).not.toHaveBeenCalled()
  expect(location.href).toBe(before)
})
