import { expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../src/App.vue'
import { api } from '../src/api'

vi.mock('../src/api',()=>({
  ApiError:class extends Error {},
  api:{dashboard:vi.fn(),getLayout:vi.fn()},
}))

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
