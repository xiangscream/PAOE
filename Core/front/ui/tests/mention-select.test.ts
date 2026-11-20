import { describe, expect, it } from 'vitest'
import {
  memberCandidates, observerNote, outsideCandidates, presenceInfo,
  rosterEntry, scopeText, staffId,
} from '../../mention-select.mjs'

describe('presenceInfo', () => {
  it('labels online and offline with a wake hint only for offline', () => {
    expect(presenceInfo('online')).toEqual({value:'online', label:'在线', wakeHint:''})
    expect(presenceInfo('offline')).toEqual({value:'offline', label:'离线', wakeHint:'将唤醒'})
  })
  it('maps anything unconfirmed to unknown, never to offline', () => {
    for (const input of [undefined, null, '', 'away', 0]) {
      expect(presenceInfo(input)).toEqual({value:'unknown', label:'状态未知', wakeHint:''})
    }
  })
})

type Member = {home_id: string}
const ids = (list: Member[]) => list.map((member: Member) => member.home_id)

describe('memberCandidates', () => {
  const members = [
    {home_id:'human', state:'participant', presence:'online'},
    {home_id:'S070', state:'participant', presence:'offline'},
    {home_id:'S071', state:'participant'},                       // 旧房无 presence → unknown
    {home_id:'S069', state:'participant', presence:'online'},
    {home_id:'S072', state:'observer', presence:'online'},       // 旁听：明确不在任务组
    {home_id:'S073', state:'left', presence:'online'},          // 已退席
  ]
  it('offers only task-group participants: online first, unknown next, offline last', () => {
    expect(ids(memberCandidates(members)))
      .toEqual(['S069', 'S071', 'S070'])
  })
  it('never lists observers, left members or the human seat', () => {
    const ids = memberCandidates(members).map((member: Member) => member.home_id)
    expect(ids).not.toContain('S072')
    expect(ids).not.toContain('S073')
    expect(ids).not.toContain('human')
  })
  it('filters by staff number or seat label', () => {
    const labelled = [{home_id:'S075', state:'participant', label:'视觉导演'}]
    expect(ids(memberCandidates(labelled, '075'))).toEqual(['S075'])
    expect(ids(memberCandidates(labelled, '导演'))).toEqual(['S075'])
    expect(memberCandidates(labelled, 'S077')).toEqual([])
  })
})

describe('rosterEntry (Rooter 名册口径)', () => {
  it('marks observers as 旁听，不在任务组 with the explicit reason', () => {
    const entry = rosterEntry({state:'observer', presence:'online'})
    expect(entry.kind).toBe('observer')
    expect(entry.presenceLabel).toBe('旁听，不在任务组')
    expect(entry.detail).toContain('退出执行与提醒范围')
    expect(entry.wakeHint).toBe('')
  })
  it('marks left as 已退席 and participants by presence', () => {
    expect(rosterEntry({state:'left', presence:'online'}).presenceLabel).toBe('已退席')
    expect(rosterEntry({state:'participant', presence:'offline'})).toMatchObject({kind:'participant', presenceLabel:'离线', wakeHint:'将唤醒'})
    expect(rosterEntry({state:'participant'}).presenceLabel).toBe('状态未知')
  })
  it('observerNote exposes the observer count as the no-remind reason', () => {
    expect(observerNote([{state:'observer'}, {state:'participant'}])).toBe('另有 1 位旁听不在提醒范围')
    expect(observerNote([{state:'participant'}])).toBe('')
  })
})

describe('outsideCandidates', () => {
  const people = [
    {staff_number:'S080', name:'编外顾问', roles:['咨询']},
    {staff_number:'S069', name:'在场成员'},
    {home_id:'legacy-2', staff_number:'S081', name:'旧号同事'},
  ]
  const members = [{home_id:'S069', state:'participant'}]
  it('requires a query and never offers seated colleagues', () => {
    expect(outsideCandidates(people, members, '')).toEqual([])
    expect(outsideCandidates(people, members, '069')).toEqual([])
    expect(outsideCandidates([{home_id:'S069', legacy_home_ids:['3002-s069'], name:'在场成员'}],
      [{home_id:'3002-s069'}], '069')).toEqual([])
  })
  it('matches by staff number, name and role', () => {
    expect(outsideCandidates(people, members, '080').map(staffId)).toEqual(['S080'])
    expect(outsideCandidates(people, members, '顾问').map(staffId)).toEqual(['S080'])
    expect(outsideCandidates(people, members, '咨询').map(staffId)).toEqual(['S080'])
    expect(outsideCandidates(people, members, '081').map(staffId)).toEqual(['S081'])
  })
})

describe('scopeText (只复述 preview 事实)', () => {
  it('describes all/selected/none/unavailable without guessing', () => {
    expect(scopeText({recipient_mode:'all', recipients:['S069','S070','S071']})).toBe('提醒全房 · 3 位成员')
    expect(scopeText({recipient_mode:'selected', recipients:['S069']})).toBe('点名提醒 1 人')
    expect(scopeText({recipient_mode:'none', recipients:[]})).toBe('普通发言 · 静默')
    expect(scopeText({unavailable:true})).toBe('收件预览暂不可用')
    expect(scopeText(null)).toBe('')
  })
})
