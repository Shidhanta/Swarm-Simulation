let currentExperiment = null;
let currentTick = 0;
let tickCache = {};
let metricsData = {};
let beliefsData = {};
let eventsData = [];
let ticksSummary = [];
let visNetwork = null;

const plotLayout = {
    paper_bgcolor: '#1a1a2e',
    plot_bgcolor: '#1a1a2e',
    font: { color: '#e0e0e0', size: 11 },
    margin: { t: 30, b: 40, l: 50, r: 20 },
    xaxis: { gridcolor: '#0f3460', zerolinecolor: '#0f3460' },
    yaxis: { gridcolor: '#0f3460', zerolinecolor: '#0f3460' },
};

const plotConfig = { responsive: true, displayModeBar: false };

async function api(path) {
    const res = await fetch(path);
    if (!res.ok) return null;
    return res.json();
}

async function init() {
    const experiments = await api('/api/experiments');
    const select = document.getElementById('experiment-select');
    if (!experiments || experiments.length === 0) {
        select.innerHTML = '<option>No experiments found</option>';
        return;
    }
    select.innerHTML = experiments.map(e =>
        `<option value="${e.name}">${e.name}</option>`
    ).join('');
    select.addEventListener('change', () => loadExperiment(select.value));

    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    document.getElementById('tick-slider').addEventListener('input', (e) => {
        currentTick = parseInt(e.target.value);
        document.getElementById('tick-display').textContent = currentTick;
        onTickChange(currentTick);
    });

    await loadExperiment(experiments[0].name);
}

async function loadExperiment(name) {
    currentExperiment = name;
    currentTick = 0;
    tickCache = {};

    const [config, ticks, metrics, events, beliefs] = await Promise.all([
        api(`/api/experiment/${name}/config`),
        api(`/api/experiment/${name}/ticks`),
        api(`/api/experiment/${name}/metrics`),
        api(`/api/experiment/${name}/events`),
        api(`/api/experiment/${name}/beliefs`),
    ]);

    ticksSummary = ticks || [];
    metricsData = metrics || {};
    eventsData = events || [];
    beliefsData = beliefs || {};

    const maxTick = ticksSummary.length - 1;
    const slider = document.getElementById('tick-slider');
    slider.max = Math.max(maxTick, 0);
    slider.value = 0;
    document.getElementById('tick-display').textContent = '0';
    document.getElementById('tick-max').textContent = `/ ${maxTick}`;

    renderTimeline();
    renderSummary(config);
    renderBeliefs();
    renderMetrics();
    renderInteractions();
    onTickChange(0);
}

function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelector(`.tab[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`panel-${tabName}`).classList.add('active');
}

function renderTimeline() {
    const container = document.getElementById('timeline');
    const eventTicks = new Set(eventsData.map(e => e.tick));
    let html = '';
    for (let i = 0; i < ticksSummary.length; i++) {
        const t = ticksSummary[i];
        const hasEvent = eventTicks.has(t.tick);
        const cls = hasEvent ? 'timeline-item has-event' : 'timeline-item';
        const badge = hasEvent ? `<span class="timeline-event-badge">E</span>` : '';
        html += `<div class="${cls}" data-tick="${t.tick}" onclick="jumpToTick(${t.tick})">
            <span>Tick ${t.tick}</span>${badge}
        </div>`;
    }
    container.innerHTML = html;
}

function jumpToTick(tick) {
    currentTick = tick;
    document.getElementById('tick-slider').value = tick;
    document.getElementById('tick-display').textContent = tick;
    onTickChange(tick);
    document.querySelectorAll('.timeline-item').forEach(el => {
        el.classList.toggle('active', parseInt(el.dataset.tick) === tick);
    });
}

async function onTickChange(tick) {
    document.getElementById('beliefs-tick-label').textContent = tick;
    document.getElementById('network-tick-label').textContent = tick;
    document.getElementById('conv-tick-label').textContent = tick;

    updateBeliefHighlight(tick);

    if (!tickCache[tick]) {
        const [network, conversations] = await Promise.all([
            api(`/api/experiment/${currentExperiment}/network/${tick}`),
            api(`/api/experiment/${currentExperiment}/conversations/${tick}`),
        ]);
        tickCache[tick] = { network, conversations };
    }

    renderNetwork(tickCache[tick].network);
    renderConversations(tickCache[tick].conversations);
}

function renderSummary(config) {
    const exp = config?.experiment || {};
    const domain = config?.domain || {};
    const sim = config?.simulation || {};
    const topo = config?.topology || {};

    let configHtml = `
        <div><strong>Description:</strong> ${exp.description || 'N/A'}</div>
        <div><strong>Agents:</strong> ${config?.agents?.count || '?'}</div>
        <div><strong>Topology:</strong> ${topo.type || '?'}</div>
        <div><strong>Mode:</strong> ${domain.interaction_mode || '?'}
            (mu=${domain.convergence_rate || '?'}, eps=${domain.confidence_bound || '?'})</div>
        <div><strong>Stubbornness:</strong> ${domain.stubbornness || '?'}</div>
        <div><strong>Seed:</strong> ${sim.seed || '?'}</div>
    `;
    if (domain.groups) {
        configHtml += '<div><strong>Groups:</strong></div>';
        domain.groups.forEach(g => {
            configHtml += `<div style="margin-left:16px">${g.name}: count=${g.count}, range=${JSON.stringify(g.range)}, stubbornness=${g.stubbornness}</div>`;
        });
    }
    document.getElementById('config-content').innerHTML = configHtml;

    const last = ticksSummary[ticksSummary.length - 1] || {};
    const first = ticksSummary[0] || {};
    document.getElementById('result-content').innerHTML = `
        <div><strong>Ticks:</strong> ${ticksSummary.length}</div>
        <div><strong>Final variance:</strong> ${last.variance?.toFixed(4) || '?'}</div>
        <div><strong>Final mean:</strong> ${last.mean_belief?.toFixed(4) || '?'}</div>
        <div><strong>Variance change:</strong> ${((last.variance - first.variance) || 0).toFixed(4)}</div>
    `;

    let eventsHtml = eventsData.length === 0
        ? '<div style="color:#888">No emergence events detected.</div>'
        : eventsData.map(e =>
            `<div class="event-item"><span class="event-tick">[tick ${e.tick}]</span> ${e.event_type}: ${e.description}</div>`
        ).join('');
    document.getElementById('events-content').innerHTML = eventsHtml;

    const keyMetrics = ['consensus', 'variance', 'polarization_bc', 'modularity',
                        'echo_chamber_index', 'algebraic_connectivity'];
    let sparkHtml = '';
    keyMetrics.forEach(name => {
        const series = metricsData[name];
        if (!series || series.length === 0) return;
        const last = series[series.length - 1];
        sparkHtml += `<div class="sparkline-card">
            <div class="sparkline-label">${name.replace(/_/g, ' ')}</div>
            <div class="sparkline-value">${last.toFixed(4)}</div>
            <div id="spark-${name}" style="height:40px"></div>
        </div>`;
    });
    document.getElementById('sparklines-content').innerHTML = sparkHtml;

    keyMetrics.forEach(name => {
        const series = metricsData[name];
        if (!series || series.length === 0) return;
        Plotly.newPlot(`spark-${name}`, [{
            y: series, mode: 'lines',
            line: { color: '#e94560', width: 1.5 },
        }], {
            ...plotLayout,
            margin: { t: 0, b: 0, l: 0, r: 0 },
            xaxis: { visible: false },
            yaxis: { visible: false },
            height: 40,
        }, plotConfig);
    });
}

function renderBeliefs() {
    const agents = Object.keys(beliefsData);
    if (agents.length === 0) return;

    const traces = agents.map(name => {
        const values = beliefsData[name].map(v => v[0]);
        return {
            y: values,
            mode: 'lines',
            name: name,
            line: { width: 1.5 },
            opacity: 0.7,
        };
    });

    Plotly.newPlot('beliefs-trajectory-plot', traces, {
        ...plotLayout,
        height: 350,
        yaxis: { ...plotLayout.yaxis, title: 'Belief', range: [-0.05, 1.05] },
        xaxis: { ...plotLayout.xaxis, title: 'Tick' },
        showlegend: true,
        legend: { font: { size: 9 }, bgcolor: 'transparent' },
    }, plotConfig);
}

function updateBeliefHighlight(tick) {
    const agents = Object.keys(beliefsData);
    if (agents.length === 0) return;

    const opinions = agents.map(name => {
        const vals = beliefsData[name];
        return tick < vals.length ? vals[tick][0] : vals[vals.length - 1][0];
    });

    Plotly.newPlot('beliefs-histogram-plot', [{
        x: opinions,
        type: 'histogram',
        nbinsx: 20,
        marker: { color: '#e94560' },
    }], {
        ...plotLayout,
        height: 200,
        xaxis: { ...plotLayout.xaxis, title: 'Belief', range: [-0.05, 1.05] },
        yaxis: { ...plotLayout.yaxis, title: 'Count' },
    }, plotConfig);
}

function renderNetwork(networkData) {
    if (!networkData || !networkData.nodes.length) {
        document.getElementById('network-graph').innerHTML = '<div style="padding:20px;color:#888">No network data available.</div>';
        return;
    }

    const nodes = networkData.nodes.map(n => {
        const belief = n.belief[0] || 0.5;
        const r = Math.round(255 * belief);
        const b = Math.round(255 * (1 - belief));
        return {
            id: n.id,
            label: n.name,
            color: { background: `rgb(${r}, 100, ${b})`, border: '#333' },
            font: { color: '#e0e0e0', size: 10 },
        };
    });

    const edges = networkData.edges.map(e => ({
        from: e.source,
        to: e.target,
        color: { color: '#333', opacity: 0.4 },
    }));

    const container = document.getElementById('network-graph');

    if (visNetwork) {
        visNetwork.setData({ nodes, edges });
    } else {
        visNetwork = new vis.Network(container, { nodes, edges }, {
            physics: { stabilization: { iterations: 100 } },
            nodes: { shape: 'dot', size: 12 },
            edges: { width: 1 },
            interaction: { hover: true },
        });
    }

    const stats = document.getElementById('network-stats');
    stats.innerHTML = `
        <div>Nodes: ${nodes.length}</div>
        <div>Edges: ${edges.length}</div>
    `;
}

function renderMetrics() {
    const names = Object.keys(metricsData);
    if (names.length === 0) return;

    const select = document.getElementById('metric-select');
    select.innerHTML = names.map(n => `<option value="${n}">${n.replace(/_/g, ' ')}</option>`).join('');
    select.addEventListener('change', () => renderMetricDetail(select.value));

    renderMetricDetail(names[0]);

    let gridHtml = '';
    names.forEach(name => {
        gridHtml += `<div class="mini-chart" id="mini-${name}"></div>`;
    });
    document.getElementById('metric-grid').innerHTML = gridHtml;

    names.forEach(name => {
        const series = metricsData[name];
        Plotly.newPlot(`mini-${name}`, [{
            y: series, mode: 'lines',
            line: { color: '#e94560', width: 1 },
        }], {
            ...plotLayout,
            height: 110,
            margin: { t: 20, b: 20, l: 40, r: 10 },
            title: { text: name.replace(/_/g, ' '), font: { size: 10, color: '#888' } },
        }, plotConfig);
    });
}

function renderMetricDetail(name) {
    const series = metricsData[name];
    if (!series) return;

    const traces = [{
        y: series,
        mode: 'lines',
        line: { color: '#e94560', width: 2 },
        name: name,
    }];

    const shapes = eventsData
        .filter(e => e.event_type.includes(name) || name.includes(e.event_type))
        .map(e => ({
            type: 'line', x0: e.tick, x1: e.tick, y0: 0, y1: 1,
            yref: 'paper', line: { color: '#f87171', dash: 'dash', width: 1 },
        }));

    Plotly.newPlot('metric-detail-plot', traces, {
        ...plotLayout,
        height: 300,
        xaxis: { ...plotLayout.xaxis, title: 'Tick' },
        yaxis: { ...plotLayout.yaxis, title: name.replace(/_/g, ' ') },
        shapes: shapes,
    }, plotConfig);
}

function renderInteractions() {
    if (ticksSummary.length === 0) return;

    const agents = Object.keys(beliefsData);
    const n = agents.length;
    if (n === 0) return;

    const matrix = Array.from({ length: n }, () => Array(n).fill(0));
    const agentIdx = {};
    agents.forEach((a, i) => agentIdx[a] = i);

    ticksSummary.forEach((_, tickIdx) => {
        const tick = tickCache[tickIdx];
        if (tick && tick.conversations) {
            tick.conversations.forEach(conv => {
                const ai = agentIdx[conv.agent_a];
                const bi = agentIdx[conv.agent_b];
                if (ai !== undefined && bi !== undefined) {
                    matrix[ai][bi]++;
                    matrix[bi][ai]++;
                }
            });
        }
    });

    Plotly.newPlot('interaction-heatmap-plot', [{
        z: matrix,
        x: agents,
        y: agents,
        type: 'heatmap',
        colorscale: [[0, '#1a1a2e'], [1, '#e94560']],
    }], {
        ...plotLayout,
        height: 400,
        xaxis: { ...plotLayout.xaxis, tickangle: -45, tickfont: { size: 9 } },
        yaxis: { ...plotLayout.yaxis, tickfont: { size: 9 } },
    }, plotConfig);
}

function renderConversations(conversations) {
    const container = document.getElementById('conversation-list');
    if (!conversations || conversations.length === 0) {
        container.innerHTML = '<div style="color:#888;padding:12px">No conversations at this tick.</div>';
        return;
    }

    let html = '';
    conversations.forEach(conv => {
        html += `<div class="conversation-card">
            <div class="conversation-header">${conv.agent_a} &harr; ${conv.agent_b}
                <span style="color:#888;font-weight:normal;font-size:11px"> &mdash; ${conv.topic || ''}</span>
            </div>`;
        conv.turns.forEach((turn, i) => {
            const side = i % 2 === 0 ? 'left' : 'right';
            html += `<div class="conversation-turn ${side}">
                <div class="turn-speaker">${turn.speaker}</div>
                <div>${turn.content}</div>
            </div>`;
        });
        html += `</div>`;
    });
    container.innerHTML = html;
}

window.jumpToTick = jumpToTick;
document.addEventListener('DOMContentLoaded', init);
