const app = document.querySelector('#app')
const topMeta = document.querySelector('#top-meta')
const imagePattern = /!\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)/g

function element(tag, className, text) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined) node.textContent = text
  return node
}

function normaliseBody(body) {
  return String(body || '')
    .replace(/<img\b[^>]*\bsrc=["'](https?:\/\/[^"']+)["'][^>]*>/gi, '\n![]($1)\n')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(?:p|div|li|h[1-6])>/gi, '\n')
    .replace(/<\/?[a-z][^>]*>/gi, '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
}

function sourceContent(body) {
  const container = element('div', 'source-content')
  for (const rawLine of normaliseBody(body).split('\n')) {
    const images = [...rawLine.matchAll(imagePattern)].map(match => ({ alt: match[1] || '来源图表', url: match[2] }))
    const text = rawLine.replace(imagePattern, '').replaceAll('**', '').trim()
    if (text) {
      if (text.startsWith('### ')) container.append(element('h4', '', text.slice(4)))
      else if (/^\d+\.\s/.test(text)) container.append(element('p', 'point', text))
      else if (/^\*\s+/.test(text)) container.append(element('p', 'bullet', text.slice(2)))
      else container.append(element('p', '', text))
    }
    for (const image of images) {
      const figure = element('figure', 'source-image')
      const link = element('a')
      link.href = image.url
      link.target = '_blank'
      link.rel = 'noreferrer'
      const img = element('img')
      img.src = image.url
      img.alt = image.alt
      img.loading = 'lazy'
      img.referrerPolicy = 'no-referrer'
      link.append(img)
      figure.append(link)
      container.append(figure)
    }
  }
  return container
}

function sourceRow(source) {
  const details = element('details', 'source')
  const summary = element('summary')
  summary.append(
    element('code', 'source-key', source.key),
    element('span', 'source-title', source.title),
    element('small', 'institution', source.institution || ''),
    element('span', 'toggle'),
  )
  const body = element('div', 'source-body')
  body.append(element('time', '', source.publishedAt || ''), sourceContent(source.body))
  details.append(summary, body)
  return details
}

function sourcesBlock(keys, sources) {
  const block = element('div', 'sources')
  block.append(element('div', 'sources-title', '来源：'))
  for (const key of keys || []) {
    if (sources[key]) block.append(sourceRow(sources[key]))
  }
  return block
}

function narrativeCard(narrative, index, eventsById, sources) {
  const article = element('article', 'narrative')
  const heading = element('h3')
  heading.append(element('span', 'number', `${index}.`), document.createTextNode(` ${narrative.headline}`))
  article.append(heading)
  for (const [label, value] of [['驱动：', narrative.drivers], ['传导：', narrative.transmission], ['定价：', narrative.pricing]]) {
    const paragraph = element('p', 'body-copy')
    paragraph.append(element('b', 'label', label), document.createTextNode(value || ''))
    article.append(paragraph)
  }
  const grid = element('div', 'signal-grid')
  const watch = element('div', 'signal-block')
  watch.append(element('b', 'label', '观察点：'))
  const list = element('ul')
  for (const point of narrative.watchpoints || []) list.append(element('li', '', point))
  watch.append(list)
  const refs = element('div', 'signal-block')
  refs.append(element('b', 'label', '事件：'))
  const refList = element('div', 'event-refs')
  for (const id of narrative.eventIds || []) {
    const row = element('span', 'event-ref')
    row.append(element('code', '', id), document.createTextNode(eventsById[id]?.headline || ''))
    refList.append(row)
  }
  refs.append(refList)
  grid.append(watch, refs)
  article.append(grid, sourcesBlock(narrative.sourceKeys, sources))
  return article
}

function eventCard(event, sources) {
  const article = element('article', 'event')
  const header = element('header')
  header.append(element('div', 'rank', `#${event.rank}`))
  const heading = element('div')
  heading.append(element('h3', '', event.headline))
  const metrics = element('p', 'metrics')
  metrics.append(
    element('code', '', event.id),
    document.createTextNode(` · ${event.sector} · 综合 ${Number(event.score).toFixed(2)}/5 · 影响 ${event.marketImpact} / 新颖 ${event.novelty} / 证据 ${event.evidenceStrength} / 可操作 ${event.actionability}`),
  )
  heading.append(metrics)
  header.append(heading)
  article.append(header, element('p', 'body-copy event-summary', event.summary || ''))
  const reasons = element('div', 'event-reasons')
  for (const [label, value] of [['为什么是今天：', event.whyNow], ['排序理由：', event.rankingReason]]) {
    const paragraph = element('p')
    paragraph.append(element('b', 'label', label), document.createTextNode(value || ''))
    reasons.append(paragraph)
  }
  article.append(reasons, sourcesBlock(event.sourceKeys, sources))
  return article
}

function deepDiveSection(deepDive) {
  const body = element('div', 'deep-dive')
  body.append(element('h3', '', '机构分歧'))
  if ((deepDive.disagreements || []).length === 0) body.append(element('p', '', '无满足硬门槛的机构分歧。'))
  for (const item of deepDive.disagreements || []) {
    body.append(element('p', '', item.topic))
    for (const view of item.views || []) body.append(element('p', '', `${view.org}：${view.view}`))
    if (item.resolution) body.append(element('p', '', `可检验点：${item.resolution}`))
  }
  body.append(element('h3', '', '反常识观点'))
  if ((deepDive.contrarian || []).length === 0) body.append(element('p', '', '无。'))
  const contrarian = element('ul')
  for (const item of deepDive.contrarian || []) contrarian.append(element('li', '', `主流认知「${item.consensus}」；反方：${item.point}`))
  body.append(contrarian)
  body.append(element('h3', '', '数据拐点'))
  if ((deepDive.inflections || []).length === 0) body.append(element('p', '', '无。'))
  const inflections = element('ul')
  for (const item of deepDive.inflections || []) inflections.append(element('li', '', `${item.point} — ${item.signal_or_noise}`))
  body.append(inflections)
  return body
}

function section(title) {
  const node = element('section', 'section')
  node.append(element('h2', '', title))
  return node
}

function validate(data) {
  if (data.schemaVersion !== 1) throw new Error(`不支持的简报版本：${data.schemaVersion}`)
  if (!data.meta?.briefDate || !Array.isArray(data.events) || !data.sources) throw new Error('简报数据不完整')
  if (data.meta.sourceBodiesIncluded !== true) throw new Error('当前快照没有包含完整 report')
}

function render(data) {
  validate(data)
  document.title = `Wisburg 每日简报 · ${data.meta.briefDate}`
  topMeta.textContent = `Brief V${data.schemaVersion} · ${data.meta.briefDate}`
  app.replaceChildren()
  const title = element('div', 'page-title')
  title.append(
    element('h1', '', `Wisburg 每日简报 · ${data.meta.briefDate}`),
    element('p', '', `原始 ${data.meta.rawItemCount} 条 · 去重后 ${data.meta.itemCount} 条 · 聚合为 ${data.meta.eventCount} 个全日事件`),
  )
  app.append(title)
  const eventsById = Object.fromEntries(data.events.map(event => [event.id, event]))
  const narratives = section('一、今日核心叙事')
  data.narratives.forEach((item, index) => narratives.append(narrativeCard(item, index + 1, eventsById, data.sources)))
  const events = section('二、全日事件排序')
  data.events.forEach(item => events.append(eventCard(item, data.sources)))
  const deepDive = section('三、值得深挖')
  deepDive.append(deepDiveSection(data.deepDive || {}))
  app.append(narratives, events, deepDive)
}

fetch(`./data/latest.json?v=${Date.now()}`, { cache: 'no-store' })
  .then(response => {
    if (!response.ok) throw new Error(`最新简报尚未发布（${response.status}）`)
    return response.json()
  })
  .then(render)
  .catch(error => {
    app.replaceChildren(element('div', 'state', error instanceof Error ? error.message : '简报加载失败'))
  })

