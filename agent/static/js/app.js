let charts = {};

// Chart update function
function updateMetricsCharts(metrics) {
    if (!metrics || !Array.isArray(metrics) || metrics.length === 0) return;

    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        elements: {
            line: {
                tension: 0.4
            }
        },
        interaction: {
            mode: 'nearest',
            axis: 'x',
            intersect: false
        },
        plugins: {
            legend: {
                display: false
            }
        },
        scales: {
            x: {
                type: 'time',
                time: {
                    unit: 'minute',
                    tooltipFormat: 'll HH:mm', // e.g., Sep 4, 2023 5:23 PM
                    displayFormats: {
                        minute: 'HH:mm', // 15:20
                        hour: 'HH:mm',   // 15:00
                        day: 'MMM D'     // Sep 4
                    }
                },
                title: {
                    display: true,
                    text: 'Time'
                },
                adapters: {
                    date: {
                        locale: 'en'
                    }
                }
            },
            y: {
                beginAtZero: true,
                max: 100,
                title: {
                    display: true,
                    text: 'Percentage (%)'
                }
            }
        }
    };

    // Network chart options for showing transfer rates
    const networkOptions = {
        ...commonOptions,
        scales: {
            ...commonOptions.scales,
            y: {
                beginAtZero: true,
                title: {
                    display: true,
                    text: 'MB/s'
                }
            }
        },
        plugins: {
            legend: {
                display: true,
                position: 'top'
            },
            tooltip: {
                callbacks: {
                    label: function(context) {
                        return `${context.dataset.label}: ${context.parsed.y} MB/s`;
                    }
                }
            }
        }
    };

    // Update current values
    const latest = metrics[metrics.length - 1];
    
    // CPU and RAM
    document.getElementById('currentCpu').textContent = `${parseFloat(latest.cpu_percent || 0).toFixed(1)}%`;
    document.getElementById('currentRam').textContent = `${parseFloat(latest.ram_percent || 0).toFixed(1)}%`;
    
    // Disk - show average usage across all disks
    if (latest.disks && Object.keys(latest.disks).length > 0) {
        const diskUsages = Object.values(latest.disks)
            .map(disk => disk.percent)
            .filter(p => typeof p === 'number'); // Ensure we only average valid numbers
        
        if (diskUsages.length > 0) {
            const avgDiskUsage = diskUsages.reduce((a, b) => a + b, 0) / diskUsages.length;
            document.getElementById('currentDisk').textContent = `${avgDiskUsage.toFixed(1)}%`;
        } else {
            document.getElementById('currentDisk').textContent = '0.0%';
        }
    } else {
        document.getElementById('currentDisk').textContent = '-';
    }
    
    // Network - show current transfer rates
    const currentNetworkRates = metrics.length > 1 ? calculateNetworkRates(latest, metrics[metrics.length - 2]) : { sent: 0, recv: 0 };
    const totalRate = currentNetworkRates.sent + currentNetworkRates.recv;
    document.getElementById('currentNetwork').textContent = `${totalRate.toFixed(1)} MB/s`;

    // Create or update charts
    // Create/update CPU and RAM charts
    const basicCharts = {
        cpu: {
            id: 'cpuChart',
            color: 'rgb(234, 88, 12)',
            data: m => m.cpu_percent
        },
        memory: {
            id: 'memoryChart',
            color: 'rgb(147, 51, 234)',
            data: m => m.ram_percent
        }
    };

    // Create or update basic charts (CPU & RAM)
    Object.entries(basicCharts).forEach(([key, chartConfig]) => {
        const chartData = {
            datasets: [{
                label: key.charAt(0).toUpperCase() + key.slice(1) + ' Usage',
                data: metrics.map(m => ({
                    x: new Date(m.timestamp * 1000),
                    y: parseFloat(chartConfig.data(m) || 0)
                })),
                borderColor: chartConfig.color,
                backgroundColor: chartConfig.color.replace(')', ', 0.1)'),
                fill: true
            }]
        };

        if (charts[key]) {
            charts[key].data = chartData;
            charts[key].update();
        } else {
            charts[key] = new Chart(document.getElementById(chartConfig.id), {
                type: 'line',
                data: chartData,
                options: commonOptions
            });
        }
    });

    // Create/update disk chart with multiple drives
    const diskOptions = {
        ...commonOptions,
        plugins: {
            legend: {
                display: true,
                position: 'top'
            },
            tooltip: {
                callbacks: {
                    label: function(context) {
                        const disk = metrics[context.dataIndex].disks[context.dataset.label];
                        if (!disk) return '';
                        
                        const usedGB = (disk.used / (1024 * 1024 * 1024)).toFixed(1);
                        const totalGB = (disk.total / (1024 * 1024 * 1024)).toFixed(1);
                        return [
                            `${context.dataset.label} (${disk.mountpoint})`,
                            `Usage: ${disk.percent.toFixed(1)}%`,
                            `${usedGB}GB / ${totalGB}GB`
                        ];
                    }
                }
            }
        }
    };

    let diskChart = charts.disk;
    if (!diskChart) {
        diskChart = new Chart(document.getElementById('diskChart'), {
            type: 'line',
            data: { datasets: [] },
            options: diskOptions
        });
        charts.disk = diskChart;
    }

    // Create datasets for each disk by finding all unique disk devices across all metrics
    if (metrics.length > 0) {
        const allDiskDevices = new Set();
        metrics.forEach(m => {
            if (m.disks) {
                Object.keys(m.disks).forEach(device => allDiskDevices.add(device));
            }
        });

        const diskDatasets = Array.from(allDiskDevices).map((device, index) => {
            const colors = [
                'rgb(59, 130, 246)', // blue
                'rgb(16, 185, 129)', // green
                'rgb(245, 158, 11)', // yellow
                'rgb(239, 68, 68)',  // red
                'rgb(168, 85, 247)'  // purple
            ];
            const color = colors[index % colors.length];
            
            return {
                label: device,
                data: metrics.map(m => ({
                    x: new Date(m.timestamp * 1000),
                    y: m.disks && m.disks[device] ? m.disks[device].percent : 0
                })),
                borderColor: color,
                backgroundColor: color.replace(')', ', 0.1)'),
                fill: true
            };
        });

        diskChart.data.datasets = diskDatasets;
        diskChart.update();
    }

    // Helper function to calculate network rates
    function calculateNetworkRates(current, previous) {
        if (!current?.network || !previous?.network) return { sent: 0, recv: 0 };
        
        const timeDiff = current.timestamp - previous.timestamp;
        if (timeDiff <= 0) return { sent: 0, recv: 0 };

        const totalBytesSent = Object.values(current.network).reduce((sum, nic) => sum + nic.bytes_sent, 0);
        const prevTotalBytesSent = Object.values(previous.network).reduce((sum, nic) => sum + nic.bytes_sent, 0);
        const bytesPerSecSent = (totalBytesSent - prevTotalBytesSent) / timeDiff;

        const totalBytesRecv = Object.values(current.network).reduce((sum, nic) => sum + nic.bytes_recv, 0);
        const prevTotalBytesRecv = Object.values(previous.network).reduce((sum, nic) => sum + nic.bytes_recv, 0);
        const bytesPerSecRecv = (totalBytesRecv - prevTotalBytesRecv) / timeDiff;

        return {
            sent: bytesPerSecSent / (1024 * 1024), // Convert to MB/s
            recv: bytesPerSecRecv / (1024 * 1024)
        };
    }

    // Calculate historical network transfer rates
    const historicalRates = metrics.map((metric, index) => {
        if (index === 0) return { sent: 0, recv: 0 };
        return calculateNetworkRates(metric, metrics[index - 1]);
    });

    // Create/update network chart with transfer rates
    const networkChartData = {
        datasets: [
            {
                label: 'Sent',
                data: metrics.map((m, i) => ({
                    x: new Date(m.timestamp * 1000),
                    y: historicalRates[i].sent.toFixed(2)
                })),
                borderColor: 'rgb(99, 102, 241)',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                fill: true
            },
            {
                label: 'Received',
                data: metrics.map((m, i) => ({
                    x: new Date(m.timestamp * 1000),
                    y: historicalRates[i].recv.toFixed(2)
                })),
                borderColor: 'rgb(251, 146, 60)',
                backgroundColor: 'rgba(251, 146, 60, 0.1)',
                fill: true
            }
        ]
    };

    if (charts.network) {
        charts.network.data = networkChartData;
        charts.network.update();
    } else {
        charts.network = new Chart(document.getElementById('networkChart'), {
            type: 'line',
            data: networkChartData,
            options: networkOptions
        });
    }
}
