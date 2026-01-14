import { useState, useEffect } from 'react';

export function useData() {
  const [posts, setPosts] = useState([]);
  const [daily, setDaily] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);

        const base = import.meta.env.BASE_URL || '/';
        const [postsRes, dailyRes, statsRes] = await Promise.all([
          fetch(`${base}data/posts.json`),
          fetch(`${base}data/daily.json`),
          fetch(`${base}data/stats.json`)
        ]);

        if (!postsRes.ok || !dailyRes.ok || !statsRes.ok) {
          throw new Error('Failed to fetch data');
        }

        const [postsData, dailyData, statsData] = await Promise.all([
          postsRes.json(),
          dailyRes.json(),
          statsRes.json()
        ]);

        setPosts(postsData);
        setDaily(dailyData);
        setStats(statsData);
        setError(null);
      } catch (err) {
        console.error('Error fetching data:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  return { posts, daily, stats, loading, error };
}

export function useFilteredData(posts, filters) {
  const [filtered, setFiltered] = useState([]);

  useEffect(() => {
    if (!posts.length) {
      setFiltered([]);
      return;
    }

    let result = [...posts];

    // Date range filter
    if (filters.dateRange) {
      const { start, end } = filters.dateRange;
      if (start) {
        result = result.filter(p => p.publishedAt >= start);
      }
      if (end) {
        result = result.filter(p => p.publishedAt <= end);
      }
    }

    // Time range filter (weeks) - skip if 'custom' or 'all'
    if (filters.timeRange && filters.timeRange !== 'all' && filters.timeRange !== 'custom') {
      const weeks = parseInt(filters.timeRange);
      if (!isNaN(weeks)) {
        const cutoffDate = new Date();
        cutoffDate.setDate(cutoffDate.getDate() - weeks * 7);
        const cutoffStr = cutoffDate.toISOString();
        result = result.filter(p => p.publishedAt >= cutoffStr);
      }
    }

    // Action type filter
    if (filters.actionType && filters.actionType !== 'all') {
      result = result.filter(p => p.actionType === filters.actionType);
    }

    // Topic filter
    if (filters.topic && filters.topic !== 'all') {
      result = result.filter(p => p.topic === filters.topic);
    }

    // Search filter
    if (filters.search) {
      const searchLower = filters.search.toLowerCase();
      result = result.filter(p =>
        p.content.toLowerCase().includes(searchLower) ||
        p.hashtags.some(h => h.toLowerCase().includes(searchLower))
      );
    }

    // Sorting
    if (filters.sortBy) {
      result.sort((a, b) => {
        let valA, valB;
        switch (filters.sortBy) {
          case 'date':
            valA = a.publishedAt;
            valB = b.publishedAt;
            break;
          case 'engagement':
            valA = a.computed.engagementRate;
            valB = b.computed.engagementRate;
            break;
          case 'reach':
            valA = a.metrics.reach;
            valB = b.metrics.reach;
            break;
          case 'shares':
            valA = a.metrics.shares;
            valB = b.metrics.shares;
            break;
          default:
            return 0;
        }
        return filters.sortOrder === 'asc' ? (valA > valB ? 1 : -1) : (valA < valB ? 1 : -1);
      });
    }

    setFiltered(result);
  }, [posts, filters]);

  return filtered;
}
