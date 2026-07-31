import * as echarts from 'echarts';


function activePane(tab: string): HTMLElement | undefined {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-dashboard-pane]'))
    .find(element => element.dataset.dashboardPane === tab);
}


function replayChart(chartElement: HTMLElement) {
  const chart = echarts.getInstanceByDom(chartElement);
  if (!chart) return;

  const option = chart.getOption() as Record<string, unknown>;
  chart.clear();
  chart.setOption({
    ...option,
    animation: true,
    animationDuration: 700,
    animationEasing: 'cubicOut',
  }, { notMerge: true, lazyUpdate: false });
  chart.resize();
}


export function replayPaneAnimations(tab: string) {
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      const pane = activePane(tab);
      if (!pane) return;

      pane.animate(
        [
          { opacity: 0.55, transform: 'translateY(8px)' },
          { opacity: 1, transform: 'translateY(0)' },
        ],
        { duration: 260, easing: 'ease-out' },
      );
      pane.querySelectorAll<HTMLElement>('[_echarts_instance_]')
        .forEach(replayChart);
    });
  });
}
