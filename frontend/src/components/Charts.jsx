import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const colors = ['#0f766e', '#14b8a6', '#fb7185', '#f59e0b', '#6366f1', '#38bdf8', '#64748b']
const gridStroke = 'rgba(148, 163, 184, 0.22)'
const axisStyle = { fontSize: 12, fill: '#64748b' }

export function EmotionDistribution({ data = {} }) {
  const rows = Object.entries(data).map(([name, value]) => ({ name, value }))
  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie dataKey="value" data={rows} innerRadius={50} outerRadius={92} paddingAngle={4} label>
          {rows.map((_, i) => <Cell key={i} fill={colors[i % colors.length]} />)}
        </Pie>
        <Tooltip contentStyle={{ borderRadius: 16, border: '1px solid rgba(148,163,184,0.25)' }} />
      </PieChart>
    </ResponsiveContainer>
  )
}

export function EngagementLine({ data = [] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
        <CartesianGrid stroke={gridStroke} strokeDasharray="4 4" />
        <XAxis dataKey="emotion" tick={axisStyle} />
        <YAxis tick={axisStyle} />
        <Tooltip contentStyle={{ borderRadius: 16, border: '1px solid rgba(148,163,184,0.25)' }} />
        <Line type="monotone" dataKey="score" stroke="#0f766e" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: '#fff' }} activeDot={{ r: 6 }} />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function StatsBars({ data = [] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} barCategoryGap={22}>
        <CartesianGrid stroke={gridStroke} strokeDasharray="4 4" vertical={false} />
        <XAxis dataKey="name" tick={axisStyle} />
        <YAxis tick={axisStyle} />
        <Tooltip contentStyle={{ borderRadius: 16, border: '1px solid rgba(148,163,184,0.25)' }} />
        <Bar dataKey="value" radius={[16, 16, 6, 6]}>
          {data.map((_, index) => <Cell key={index} fill={colors[index % colors.length]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
