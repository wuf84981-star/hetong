import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Review from './pages/Review'
import ReviewDetail from './pages/ReviewDetail'
import History from './pages/History'
import Rules from './pages/Rules'
import Templates from './pages/Templates'
import Settings from './pages/Settings'
import Regulations from './pages/Regulations'
import Knowledge from './pages/Knowledge'
import Diff from './pages/Diff'
import Negotiation from './pages/Negotiation'
import BadCaseList from './pages/BadCaseList'
import BadCaseDetail from './pages/BadCaseDetail'

// 免登录直入：所有页面游客可进，写操作由各页的 requireLogin 门把关
export default function App() {
  return (
    <Routes>
      {/* Layout 外全屏页：产品落地页与沉浸登录，不带侧栏 */}
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route element={<Layout />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/review" element={<Review />} />
        <Route path="/review/:id" element={<ReviewDetail />} />
        <Route path="/history" element={<History />} />
        <Route path="/rules" element={<Rules />} />
        <Route path="/templates" element={<Templates />} />
        <Route path="/regulations" element={<Regulations />} />
        <Route path="/knowledge" element={<Knowledge />} />
        <Route path="/diff" element={<Diff />} />
        <Route path="/negotiation" element={<Negotiation />} />
        <Route path="/bad-cases" element={<BadCaseList />} />
        <Route path="/bad-cases/:caseId" element={<BadCaseDetail />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}
