import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../src/App.vue'
import { api } from '../src/api'

vi.mock('../src/api',()=>({
  ApiError:class extends Error {},
  api:{dashboard:vi.fn(),getLayout:vi.fn()},
}))
afterEach(()=>vi.unstubAllGlobals())

it('an unregistered installation shows an actionable empty view without an invalid layout read',async()=>{
  localStorage.clear()
  history.replaceState(null,'','/')
  vi.mocked(api.dashboard).mockResolvedValue({ok:true,project:'',projects:[],agents:[],examples:{workflow:[],skill:[],tool:[]}})
  const wrapper=mount(App,{global:{stubs:{BoardCanvas:true,ChatView:true,PersonDrawer:true,LibraryPanel:true,CollaborationDialog:true,ProjectOverview:true}}})
  await flushPromises()
  expect(wrapper.text()).toContain('尚未登记项目')
  expect(wrapper.text()).toContain('团队还没有成员')
  expect(api.getLayout).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('changing project on the board forgets its previous room while explicit cross-project links remain readable',async()=>{
  localStorage.clear()
  localStorage.setItem('poe.project','1001')
  history.replaceState(null,'','/cat?room=room-a')
  const projects=[{id:'1001'},{id:'2001'}]
  vi.mocked(api.dashboard).mockImplementation(async project=>({ok:true,project:project||'1001',projects,agents:[],examples:{workflow:[],skill:[],tool:[]}}))
  vi.mocked(api.getLayout).mockImplementation(async project=>({ok:true,project,layout:{nodes:{},viewport:{x:0,y:0,zoom:1}}}))
  const room={ok:true,id:'room-a',title:'A的讨论',status:'open',members:[],messages:[{id:'a-message',seq:1,sender_id:'human',body:'原项目消息',created_at:'2026-11-07T00:00:00Z'}]}
  const fetch=vi.fn(async(path:string)=>({ok:true,json:async()=>path==='/api/cat/rooms?project=1001'?{ok:true,rooms:[{id:'room-a',title:room.title,status:'open',created_at:'2026-11-07T00:00:00Z'}]}:path.startsWith('/api/cat/rooms')?{ok:true,rooms:[]}:path==='/api/cat/people'?{ok:true,people:[]}:room}))
  vi.stubGlobal('fetch',fetch)
  vi.stubGlobal('EventSource',vi.fn(function(){return {addEventListener:vi.fn(),close:vi.fn()}}))
  vi.stubGlobal('ResizeObserver',vi.fn(function(){return {observe:vi.fn(),disconnect:vi.fn()}}))
  const options={global:{stubs:{BoardCanvas:true,PersonDrawer:true,LibraryPanel:true,CollaborationDialog:true,ProjectOverview:true}}}
  let wrapper=mount(App,options)
  await flushPromises()
  expect(wrapper.text()).toContain('原项目消息')
  await wrapper.findAll('button').find(button=>button.text()==='团队画板')!.trigger('click')
  await wrapper.get('[aria-label="选择项目"]').setValue('2001')
  await flushPromises()
  const previousReads=fetch.mock.calls.filter(([path])=>path==='/api/room/room-a').length
  await wrapper.findAll('button').find(button=>button.text()==='讨论')!.trigger('click')
  await flushPromises()
  expect(wrapper.text()).not.toContain('原项目消息')
  expect(wrapper.text()).toContain('这里还没有讨论')
  expect(new URL(location.href).searchParams.has('room')).toBe(false)
  expect(document.title).toBe('CAT · POE')
  expect(fetch.mock.calls.filter(([path])=>path==='/api/room/room-a')).toHaveLength(previousReads)
  wrapper.unmount()

  history.replaceState(null,'','/cat?room=room-a')
  wrapper=mount(App,options)
  await flushPromises()
  expect((wrapper.get('[aria-label="选择项目"]').element as HTMLSelectElement).value).toBe('2001')
  expect(wrapper.text()).toContain('原项目消息')
  expect(wrapper.text()).toContain('正在查看链接指定的其他项目讨论')
  wrapper.unmount()
})
