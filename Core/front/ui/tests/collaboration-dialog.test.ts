import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import CollaborationDialog from '../src/components/CollaborationDialog.vue'
import { api } from '../src/api'

vi.mock('../src/api',()=>({api:{collaborate:vi.fn(),collaborationFact:vi.fn()}}))
const initial={provider:'1001-s006',receiver:'1001-s005',topic:'补充资料',note:'原说明',mode:'chat' as const,remind:true,reference:null}
const props={open:true,initial,project:'1001',agents:[{id:'1001-s006',name:'提供方',can_contact:true},{id:'1001-s005',name:'接收方',can_contact:true}]}
let wrappers:VueWrapper[]=[]
const open=()=>{const wrapper=mount(CollaborationDialog,{props});wrappers.push(wrapper);return wrapper}
const button=(wrapper:VueWrapper,label:string)=>wrapper.findAll('button').find(item=>item.text()===label)!
const saved=()=>JSON.parse(localStorage.getItem('poe.collab.1001')!)

beforeEach(()=>{localStorage.clear();vi.resetAllMocks()})
afterEach(()=>{for(const wrapper of wrappers)wrapper.unmount();wrappers=[];vi.restoreAllMocks()})

describe('collaboration request continuity',()=>{
  it('locks and persists a request before POST, and reload only checks its original id',async()=>{
    vi.mocked(api.collaborate).mockImplementation(()=>new Promise(()=>{}))
    let wrapper=open()
    await button(wrapper,'发起协作').trigger('click')
    const request=vi.mocked(api.collaborate).mock.calls[0][0]
    expect(saved().messageId).toBe(request.message_id)
    expect(saved().phase).toBe('submitting')
    expect(wrapper.get('#topic').attributes('disabled')).toBeDefined()
    expect(button(wrapper,'关闭').attributes('disabled')).toBeDefined()
    wrapper.unmount();wrappers=[]
    wrapper=open()
    await flushPromises()
    expect(wrapper.text()).toContain('已恢复未完成的请求')
    expect(button(wrapper,'发起协作')).toBeUndefined()
    vi.mocked(api.collaborationFact).mockResolvedValue({ok:true,state:'not_found'})
    await button(wrapper,'核对原记录').trigger('click')
    await flushPromises()
    expect(api.collaborationFact).toHaveBeenCalledWith('1001','chat',request.message_id,undefined)
    expect(api.collaborate).toHaveBeenCalledTimes(1)
    expect(saved().state).toBe('unknown')
  })

  it('a reload during partial continuation becomes unknown and never offers another POST',async()=>{
    localStorage.setItem('poe.collab.1001',JSON.stringify({phase:'settled',project:'1001',draft:initial,messageId:'ui-original',state:'partial',text:'',result:{state:'partial',room_id:'room-original',message_id:'ui-original'}}))
    vi.mocked(api.collaborate).mockImplementation(()=>new Promise(()=>{}))
    let wrapper=open()
    await flushPromises()
    await button(wrapper,'继续原房间').trigger('click')
    expect(api.collaborate).toHaveBeenCalledWith(expect.objectContaining({room_id:'room-original',message_id:'ui-original'}))
    wrapper.unmount();wrappers=[]
    wrapper=open()
    await flushPromises()
    expect(button(wrapper,'继续原房间')).toBeUndefined()
    expect(button(wrapper,'核对原记录')).toBeDefined()
    expect(api.collaborate).toHaveBeenCalledTimes(1)
  })

  it('a corrected definite failure stores the new id before sending it',async()=>{
    vi.mocked(api.collaborate).mockResolvedValueOnce({ok:false,state:'failed',error:'成员不可联系'})
    const wrapper=open()
    await button(wrapper,'发起协作').trigger('click');await flushPromises()
    const first=vi.mocked(api.collaborate).mock.calls[0][0].message_id
    vi.mocked(api.collaborate).mockImplementation(()=>new Promise(()=>{}))
    await wrapper.get('#topic').setValue('修正后的主题')
    await button(wrapper,'发起协作').trigger('click')
    const second=vi.mocked(api.collaborate).mock.calls[1][0].message_id
    expect(second).not.toBe(first)
    expect(saved().messageId).toBe(second)
  })

  it('does not send if it cannot retain the in-flight request',async()=>{
    const wrapper=open();await flushPromises()
    vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('disk full')})
    await button(wrapper,'发起协作').trigger('click')
    expect(api.collaborate).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('本地保存失败')
  })
})
