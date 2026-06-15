export const BaZiCharts = {
    renderWuxingRadar(container, data) {
        const chart = prepareChart(container);
        if (!chart) return;
        const names = ['金', '木', '水', '火', '土'];
        chart.setOption({
            title: { text: '五行分布' },
            tooltip: {},
            radar: { indicator: names.map((name) => ({ name, max: Math.max(5, ...names.map((n) => Number(data[n] || 0))) })) },
            series: [{ type: 'radar', data: [{ value: names.map((name) => Number(data[name] || 0)), name: '五行' }] }],
        });
    },
    renderShishenPie(container, data) {
        const chart = prepareChart(container);
        if (!chart) return;
        chart.setOption({
            title: { text: '十神分布' },
            tooltip: { trigger: 'item' },
            series: [{ type: 'pie', radius: '60%', data: Object.entries(data || {}).map(([name, value]) => ({ name, value })) }],
        });
    },
    renderDayunTrend(container, data) {
        const chart = prepareChart(container);
        if (!chart) return;
        chart.setOption({
            title: { text: '大运趋势' },
            tooltip: {},
            xAxis: { type: 'category', data: (data || []).map((x) => `${x.age}岁 ${x.gan_zhi || ''}`) },
            yAxis: { type: 'value' },
            series: [{ type: 'line', smooth: true, data: (data || []).map((x) => Number(x.score || 0)) }],
        });
    },
    renderLiunianBar(container, data) {
        const chart = prepareChart(container);
        if (!chart) return;
        chart.setOption({
            title: { text: '流年运势' },
            tooltip: {},
            xAxis: { type: 'category', data: (data || []).map((x) => `${x.year} ${x.gan_zhi || ''}`) },
            yAxis: { type: 'value' },
            series: [{ type: 'bar', data: (data || []).map((x) => Number(x.score || 0)) }],
        });
    },
};

function prepareChart(container) {
    if (!container) return null;
    if (!window.echarts) {
        container.innerHTML = '<div class="chart-empty">ECharts 未加载</div>';
        return null;
    }
    return window.echarts.init(container);
}

window.BaZiCharts = BaZiCharts;
