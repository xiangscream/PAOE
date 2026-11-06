import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PersonNode from '../src/components/PersonNode.vue'
import type { AgentSummary } from '../src/types'

const agent: AgentSummary = {
  id: '3002-s035',
  number: 'S040',
  name: 'S040 前端',
  role: '前端实现',
  member_status: 'active',
  next_action: '实现统一工作台',
  pending_notices: 2,
  tasks: { doing: 1 },
  ok: true,
}

describe('PersonNode', () => {
  it('shows number, name, role, status and current action', () => {
    const wrapper = mount(PersonNode, {
      props: { data: { agent } },
      global: { stubs: { Handle: true } },
    })
    expect(wrapper.text()).toContain('S040')
    expect(wrapper.text()).toContain('前端实现')
    expect(wrapper.text()).toContain('实现统一工作台')
    expect(wrapper.text()).toContain('在岗')
  })

  it('marks paused members and does not present old TODO as executable', () => {
    const wrapper = mount(PersonNode, {
      props: { data: { agent: { ...agent, member_status: 'paused', can_contact: false } } },
      global: { stubs: { Handle: true } },
    })
    expect(wrapper.classes()).toContain('paused')
    expect(wrapper.text()).toContain('暂停')
  })
})
