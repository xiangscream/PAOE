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

it('ending an unknown send preserves its id and a late old message cannot clear new input',async()=>{
  localStorage.clear()
  history.replaceState(null,'','/cat?room=room-one')
  const fetch=vi.fn(async(path:string,options?:RequestInit)=>({ok:true,json:async()=>
    options?.method==='POST'?{ok:false,error_code:'cli_result_unknown'}:
    path.startsWith('/api/cat/rooms')?{ok:true,rooms:[{id:'room-one',title:'测试讨论',status:'open',created_at:'2026-11-07T00:00:00Z'}]}:
    path==='/api/cat/people'?{ok:true,people:[]}:{ok:true,id:'room-one',title:'测试讨论',status:'open',members:[],messages:[]}}))
  vi.stubGlobal('fetch',fetch)
  vi.stubGlobal('EventSource',vi.fn(function(){return {addEventListener:vi.fn(),close:vi.fn()}}))
  vi.stubGlobal('ResizeObserver',vi.fn(function(){return {observe:vi.fn(),disconnect:vi.fn()}}))
  let wrapper=mount(ChatView,{props:{project:'1001',initialRoom:'room-one'}})
  await flushPromises()
  const button=(label:string)=>wrapper.findAll('button').find(item=>item.text()===label)!
  await wrapper.get('#message-input').setValue('原消息')
  await wrapper.get('.composer form').trigger('submit');await flushPromises()
  const posts=()=>fetch.mock.calls.filter(([,options])=>options?.method==='POST')
  const original=JSON.parse(posts()[0][1]!.body as string).message_id
  await button('核对原消息').trigger('click');await flushPromises()
  await button('结束本地等待').trigger('click')
  await button('确认结束，写新消息').trigger('click');await flushPromises()
  expect(posts()).toHaveLength(1)
  expect(wrapper.get('#message-input').attributes('disabled')).toBeUndefined()
  expect((wrapper.get('#message-input').element as HTMLTextAreaElement).value).toBe('')
  expect(wrapper.text()).toContain(original)
  await wrapper.get('#message-input').setValue('新的内容')
  await wrapper.get('.composer form').trigger('submit');await flushPromises()
  const second=JSON.parse(posts()[1][1]!.body as string).message_id
  expect(second).not.toBe(original)
  const vm=wrapper.vm as any
  vm.state.messages.push({id:original,seq:1,sender_id:'human',body:'原消息',created_at:'2026-11-07T00:00:00Z'})
  vm.confirmPending(vm.state)
  expect(vm.state.pending.id).toBe(second)
  expect(vm.state.draft).toBe('新的内容')
  wrapper.unmount()
  wrapper=mount(ChatView,{props:{project:'1001',initialRoom:'room-one'}})
  await flushPromises()
  expect(wrapper.text()).toContain(original)
  expect((wrapper.vm as any).state.pending.id).toBe(second)
  expect(posts()).toHaveLength(2)
  wrapper.unmount()
})
