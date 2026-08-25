'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { NavItem } from './types'

const navigation: NavItem[] = [
  { name: 'Dashboard', href: '/merchant/dashboard', icon: 'dashboard' },
  { name: 'Products', href: '/merchant/products', icon: 'cube' },
  { name: 'AI Commerce Readiness', href: '/merchant/dashboard#readiness', icon: 'shield' },
  { name: 'Growth Opportunities', href: '/merchant/dashboard#growth', icon: 'chart' },
  { name: 'Settings', href: '/merchant/dashboard#settings', icon: 'cog' },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-gray-200 hidden lg:block">
      <div className="flex h-16 items-center px-6 border-b border-gray-200">
        <span className="text-xl font-bold text-indigo-600">AI Commerce</span>
      </div>
      <nav className="mt-6 px-4" aria-label="Main navigation">
        <ul className="space-y-1" role="list">
          {navigation.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + '#')
            return (
              <li key={item.name}>
                <Link
                  href={item.href}
                  className={`flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-colors ${
                    isActive
                      ? 'bg-indigo-50 text-indigo-700'
                      : 'text-gray-700 hover:bg-gray-100 hover:text-gray-900'
                  }`}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <span className="mr-3">{item.icon}</span>
                  {item.name}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>
    </aside>
  )
}